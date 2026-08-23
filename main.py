# -*- coding: utf-8 -*-
"""
法律 RAG 助手 Web 服务（M4）：纯 API 后端，与 Vue 前端分离部署。

启动（开发，双进程）：
    python main.py                     # API 在 127.0.0.1:8000
    cd frontend && npm run dev         # 前端在 5173，/api 代理到 8000

启动（演示，单进程）：
    cd frontend && npm run build
    python main.py                     # 直接开 http://127.0.0.1:8000

API（/api 前缀）：
    POST /api/chat  {"message": "...", "session_id": "..."} -> {"answer", "session_id", "trace"}
                session_id 缺省时服务端生成并返回，前端存下来续传即多轮。
"""
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import session
from agent.loop import run

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


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """单轮对话：带 history 调 agent，答案落回会话存储。"""
    sid = req.session_id or uuid.uuid4().hex
    history = session.get_history(sid)
    result = run(req.message, history=history)
    session.append(sid, "user", req.message)
    session.append(sid, "assistant", result["answer"])
    return {"answer": result["answer"], "session_id": sid, "trace": result["trace"]}


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
    """单个会话的完整对话历史。"""
    return {"session_id": sid, "history": session.get_history(sid)}


# 演示模式：前端构建产物存在才托管（SPA，API 路由挂载其后，优先匹配）
dist = PROJECT_ROOT / "frontend" / "dist"
if dist.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
