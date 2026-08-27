# -*- coding: utf-8 -*-
"""法律 RAG 助手 Web 服务：纯 API 后端，与 Vue 前端分离。
开发: python main.py + cd frontend && npm run dev（5173 代理到 8000）
演示: cd frontend && npm run build 后 python main.py 单进程直开 8000。"""
import os
import secrets
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agent import session, auth, context
from agent.loop import run
from agent.revise import revise_contract
from core import fileparse
from core.docx_export import build_docx

app = FastAPI(title="法律 RAG 助手")

# 前后端分离：dev 时前端 5173 跨源直连本 API，放行浏览器跨域。
# 生产部署到别的域名时用 CORS_ORIGINS 覆盖（逗号分隔），不再写死 localhost。
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    contract: str | None = None  # 上传的待审查合同全文（可选，作为独立上下文消息传给 agent）


class AuthRequest(BaseModel):
    username: str
    password: str


def _extract_bearer(authorization: str | None) -> str | None:
    """从 Authorization 头取 Bearer token；缺失/格式错返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):].strip()
    return token or None


def get_current_user(authorization: str | None = Header(None)) -> dict:
    """FastAPI 依赖：解析并校验 JWT，返回 {id, username}。失败一律 401。"""
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    try:
        return auth.verify_token(token)
    except Exception:  # noqa: BLE001 —— token 非法/过期都视为未认证
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")


def _init_auth() -> None:
    """启动时 seed 初始用户 + 把历史未归属会话迁移到其名下。

    INIT_USERNAME/INIT_PASSWORD 可配；未设密码则生成随机密码并打印一次，
    避免裸奔（同时也保证每次都能登进去）。幂等，重复启动安全。
    """
    username = os.environ.get("INIT_USERNAME", "admin")
    password = os.environ.get("INIT_PASSWORD")
    if not password:
        password = secrets.token_hex(8)
        print(f"[auth] 未设置 INIT_PASSWORD，为 {username} 生成随机初始密码：{password}")
    try:
        seed = auth.seed_user(username, password)
    except ValueError as e:
        print(f"[auth] 初始用户创建失败：{e}")
        return
    migrated = session.migrate_anonymous(seed["id"])
    if migrated:
        print(f"[auth] 已将 {migrated} 个历史未归属会话迁移到 {username}")


@app.post("/api/register")
def register(req: AuthRequest) -> dict:
    """开放注册：建用户并返回 token（自动登录）。用户名冲突返回 400。"""
    try:
        user = auth.register_user(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    t = auth.create_token(user)
    return {"token": t["token"], "expires_in": t["expires_in"], "username": user["username"]}


@app.post("/api/login")
def login(req: AuthRequest) -> dict:
    """登录：校验用户名/密码，成功返回 token。"""
    user = auth.authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    t = auth.create_token(user)
    return {"token": t["token"], "expires_in": t["expires_in"], "username": user["username"]}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    """返回当前登录用户（供前端启动时校验 token 是否有效）。"""
    return {"id": user["id"], "username": user["username"]}


def _history_with_contract(history: list, contract: str) -> list:
    """若会话存有待审查合同，把它作为一条独立 user 上下文消息插在问题之前，
    与用户提问分开，agent 能区分"要审的合同"和"问的问题"。合同不占对话气泡。"""
    if contract:
        return [*history, {"role": "user", "content": f"待审查合同全文如下：\n\n{contract}"}]
    return history


@app.post("/api/chat")
def chat(req: ChatRequest, user: dict = Depends(get_current_user)) -> dict:
    """单轮对话：带 history 调 agent，答案落回会话存储。

    contract 每次发送覆盖到会话（None 即移除附件 → 清空），存进 sessions 表，
    使后续正常对话与"重新生成"都能读到同一份合同。会话归属当前登录用户。
    """
    uid = user["id"]
    sid = req.session_id or uuid.uuid4().hex
    session.save_contract(uid, sid, req.contract or None)
    history = session.get_history(uid, sid)
    # 长会话先做滑动窗口+摘要压缩，再拼合同；合同永不被裁剪
    agent_history = _history_with_contract(
        context.build_history(history), session.get_contract(uid, sid)
    )
    # 先落库用户消息，再跑 agent：run 抛异常时用户消息已留痕、会话不丢，
    # 且不会因重试造成重复落库。
    user_id = session.append(uid, sid, "user", req.message)
    try:
        result = run(req.message, history=agent_history)
    except Exception as e:  # noqa: BLE001 —— LLM 超时/网络抖动，如实落一条失败留痕
        session.append(uid, sid, "assistant", f"（生成失败：{type(e).__name__}: {e}）", None)
        raise HTTPException(status_code=502, detail=f"生成失败：{e}")
    assistant_id = session.append(uid, sid, "assistant", result["answer"], result.get("citation_check"))
    return {
        "answer": result["answer"],
        "session_id": sid,
        "user_id": user_id,
        "assistant_id": assistant_id,
        "trace": result["trace"],
        "citation_check": result.get("citation_check", {}),
        "has_contract": bool(session.get_contract(uid, sid)),
    }


class TruncateRequest(BaseModel):
    from_id: int  # 截断点：删除该会话 id >= from_id 的所有消息


@app.post("/api/chat/sessions/{sid}/truncate")
def truncate_history(sid: str, req: TruncateRequest, user: dict = Depends(get_current_user)) -> dict:
    """修改重发：把会话截断到某条用户消息之前，让位给重新发送的新一轮。"""
    session.delete_from(user["id"], sid, req.from_id)
    return {"ok": True, "session_id": sid}


@app.post("/api/chat/sessions/{sid}/regenerate")
def regenerate_chat(sid: str, user: dict = Depends(get_current_user)) -> dict:
    """重新生成：删掉最后一条回答，对最后一条用户问题重新跑一遍 agent，替换原回答。"""
    uid = user["id"]
    history = session.get_history(uid, sid)
    last_user = next((m for m in reversed(history) if m["role"] == "user"), None)
    if last_user is None:
        raise HTTPException(status_code=400, detail="没有可重新生成的用户问题")
    history_before = [m for m in history if m["id"] < last_user["id"]]
    # 先跑成功，再删旧回答：生成失败时旧回答保留，不会把会话弄丢。
    result = run(
        last_user["content"],
        history=_history_with_contract(
            context.build_history(history_before), session.get_contract(uid, sid)
        ),
    )
    session.delete_after(uid, sid, last_user["id"])  # 只删旧的回答，保留最后一条用户问题
    assistant_id = session.append(uid, sid, "assistant", result["answer"], result.get("citation_check"))
    return {
        "answer": result["answer"],
        "assistant_id": assistant_id,
        "trace": result["trace"],
        "citation_check": result.get("citation_check", {}),
    }


@app.post("/api/chat/sessions/{sid}/revise-docx")
def revise_and_export_docx(sid: str, user: dict = Depends(get_current_user)) -> Response:
    """把会话里已审查的合同生成修订版，导出成 .docx 下载。

    依赖会话存有待审查合同（上传过）且已有至少一条助手审查回答；
    修订版全文 + 修改说明表（原条款/修订后/依据，依据经 M6 校验）。
    """
    uid = user["id"]
    contract = session.get_contract(uid, sid)
    if not contract.strip():
        raise HTTPException(status_code=400, detail="当前会话没有待审查合同，无法生成修订版")
    history = session.get_history(uid, sid)
    review = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
    try:
        result = revise_contract(contract, review)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"修订生成失败：{e}")
    content = build_docx(result["修订版合同"], result["修改清单"], result["有效"], result["总数"])
    filename = "修订版合同.docx"
    from urllib.parse import quote
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.post("/api/upload")
async def upload_contract(file: UploadFile = File(...), user: dict = Depends(get_current_user)) -> dict:
    """上传合同文件 → 返回提取的纯文本。审查仍走 /api/chat，本端点只做解析。"""
    data = await file.read()
    try:
        text = fileparse.extract_text(data, file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="未能从文件中提取到文本（扫描版 PDF 无文字层？），请改用 .docx / .txt 或直接粘贴。",
        )
    return {"filename": file.filename, "text": text}


@app.delete("/api/chat/sessions/{sid}")
def delete_session(sid: str, user: dict = Depends(get_current_user)) -> dict:
    """删除指定会话及其全部消息（只删自己归属的）。"""
    session.clear(user["id"], sid)
    return {"ok": True}


@app.get("/api/chat/sessions")
def list_chat_sessions(user: dict = Depends(get_current_user)) -> dict:
    """当前用户的会话摘要（按最近更新时间倒序），供前端侧栏。"""
    return {"sessions": session.list_sessions(user["id"])}


@app.get("/api/chat/sessions/{sid}/history")
def get_chat_history(sid: str, user: dict = Depends(get_current_user)) -> dict:
    """单个会话的完整对话历史；has_contract 供前端决定是否显示导出修订版按钮。

    只返回自己归属的会话；跨用户查他人 sid 得到空历史（不泄露存在性）。
    """
    return {
        "session_id": sid,
        "history": session.get_history(user["id"], sid),
        "has_contract": bool(session.get_contract(user["id"], sid)),
    }


# 启动即 seed 初始用户 + 迁移历史未归属会话（幂等）。放模块末尾，保证所有依赖已定义，
# 且 `python main.py` 与 uvicorn 直接跑都能生效。
_init_auth()

# 演示模式：前端构建产物存在才托管（SPA，API 路由挂载其后，优先匹配）
dist = PROJECT_ROOT / "frontend" / "dist"
if dist.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
