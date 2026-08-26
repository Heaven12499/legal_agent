# -*- coding: utf-8 -*-
"""法律 RAG 助手 Web 服务：纯 API 后端，与 Vue 前端分离。
开发: python main.py + cd frontend && npm run dev（5173 代理到 8000）
演示: cd frontend && npm run build 后 python main.py 单进程直开 8000。"""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from agent import session
from agent.loop import run
from agent.revise import revise_contract
from core import fileparse
from core.docx_export import build_docx

app = FastAPI(title="法律 RAG 助手")

# 前后端分离：dev 时前端 5173 跨源直连本 API，放行浏览器跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    contract: str | None = None  # 上传的待审查合同全文（可选，作为独立上下文消息传给 agent）


def _history_with_contract(history: list, contract: str) -> list:
    """若会话存有待审查合同，把它作为一条独立 user 上下文消息插在问题之前，
    与用户提问分开，agent 能区分"要审的合同"和"问的问题"。合同不占对话气泡。"""
    if contract:
        return [*history, {"role": "user", "content": f"待审查合同全文如下：\n\n{contract}"}]
    return history


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """单轮对话：带 history 调 agent，答案落回会话存储。

    contract 每次发送覆盖到会话（None 即移除附件 → 清空），存进 sessions 表，
    使后续正常对话与"重新生成"都能读到同一份合同。
    """
    sid = req.session_id or uuid.uuid4().hex
    session.save_contract(sid, req.contract or None)
    history = session.get_history(sid)
    agent_history = _history_with_contract(history, session.get_contract(sid))
    result = run(req.message, history=agent_history)
    user_id = session.append(sid, "user", req.message)
    assistant_id = session.append(sid, "assistant", result["answer"], result.get("citation_check"))
    return {
        "answer": result["answer"],
        "session_id": sid,
        "user_id": user_id,
        "assistant_id": assistant_id,
        "trace": result["trace"],
        "citation_check": result.get("citation_check", {}),
        "has_contract": bool(session.get_contract(sid)),
    }


class TruncateRequest(BaseModel):
    from_id: int  # 截断点：删除该会话 id >= from_id 的所有消息


@app.post("/api/chat/sessions/{sid}/truncate")
def truncate_history(sid: str, req: TruncateRequest) -> dict:
    """修改重发：把会话截断到某条用户消息之前，让位给重新发送的新一轮。"""
    session.delete_from(sid, req.from_id)
    return {"ok": True, "session_id": sid}


@app.post("/api/chat/sessions/{sid}/regenerate")
def regenerate_chat(sid: str) -> dict:
    """重新生成：删掉最后一条回答，对最后一条用户问题重新跑一遍 agent，替换原回答。"""
    history = session.get_history(sid)
    last_user = next((m for m in reversed(history) if m["role"] == "user"), None)
    if last_user is None:
        raise HTTPException(status_code=400, detail="没有可重新生成的用户问题")
    session.delete_after(sid, last_user["id"])  # 只删旧的回答，保留最后一条用户问题
    history_before = [m for m in history if m["id"] < last_user["id"]]
    result = run(
        last_user["content"],
        history=_history_with_contract(history_before, session.get_contract(sid)),
    )
    assistant_id = session.append(sid, "assistant", result["answer"], result.get("citation_check"))
    return {
        "answer": result["answer"],
        "assistant_id": assistant_id,
        "trace": result["trace"],
        "citation_check": result.get("citation_check", {}),
    }


@app.post("/api/chat/sessions/{sid}/revise-docx")
def revise_and_export_docx(sid: str) -> Response:
    """把会话里已审查的合同生成修订版，导出成 .docx 下载。

    依赖会话存有待审查合同（上传过）且已有至少一条助手审查回答；
    修订版全文 + 修改说明表（原条款/修订后/依据，依据经 M6 校验）。
    """
    contract = session.get_contract(sid)
    if not contract.strip():
        raise HTTPException(status_code=400, detail="当前会话没有待审查合同，无法生成修订版")
    history = session.get_history(sid)
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
async def upload_contract(file: UploadFile = File(...)) -> dict:
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
def delete_session(sid: str) -> dict:
    """删除指定会话及其全部消息。"""
    session.clear(sid)
    return {"ok": True}


@app.get("/api/chat/sessions")
def list_chat_sessions() -> dict:
    """所有会话摘要（按最近更新时间倒序），供前端侧栏。"""
    return {"sessions": session.list_sessions()}


@app.get("/api/chat/sessions/{sid}/history")
def get_chat_history(sid: str) -> dict:
    """单个会话的完整对话历史；has_contract 供前端决定是否显示导出修订版按钮。"""
    return {
        "session_id": sid,
        "history": session.get_history(sid),
        "has_contract": bool(session.get_contract(sid)),
    }


# 演示模式：前端构建产物存在才托管（SPA，API 路由挂载其后，优先匹配）
dist = PROJECT_ROOT / "frontend" / "dist"
if dist.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
