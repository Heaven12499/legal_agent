# -*- coding: utf-8 -*-
"""会话存储：SQLite 持久化（标准库 sqlite3，零第三方依赖），重启不丢。

与旧内存版公开接口一致：get_history / append / clear / list_sessions。
每个操作开短连接（closing + 事务上下文），天然线程安全——
FastAPI 同步端点跑在线程池，各线程各开各的连接。
"""
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


def _db_path() -> Path:
    """数据库文件：SESSION_DB 环境变量可覆盖（测试用临时库），默认 data/sessions.db。"""
    env = os.environ.get("SESSION_DB")
    return Path(env) if env else PROJECT_ROOT / "data" / "sessions.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)  # 幂等建表，每次连接保证表在
    return conn


def get_history(session_id: str) -> list[dict]:
    """返回该会话的对话历史（用户/助手干净轮次），无则空列表。"""
    with closing(_connect()) as conn, conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [{"role": r, "content": c} for r, c in rows]


def append(session_id: str, role: str, content: str) -> None:
    """追加一轮（role: user/assistant），会话不存在则创建，更新 updated_at。"""
    now = time.time()
    with closing(_connect()) as conn, conn:
        # 保留首次 created_at，只刷新 updated_at
        conn.execute(
            "INSERT INTO sessions(session_id, created_at, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, now, now),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content) VALUES(?, ?, ?)",
            (session_id, role, content),
        )


def clear(session_id: str) -> None:
    """清空某会话（sessions + messages 两表一起删）。"""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))


def list_sessions() -> list[dict]:
    """所有会话摘要，按最近更新时间倒序。"""
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT s.session_id, s.created_at, s.updated_at,
                   (SELECT m.content FROM messages m
                     WHERE m.session_id = s.session_id
                     ORDER BY m.id LIMIT 1) AS first_message,
                   (SELECT COUNT(*) FROM messages m
                     WHERE m.session_id = s.session_id) AS message_count
            FROM sessions s
            ORDER BY s.updated_at DESC
            """
        ).fetchall()
    return [
        {
            "session_id": sid,
            "first_message": first_message or "",
            "message_count": count,
            "created_at": created,
            "updated_at": updated,
        }
        for sid, created, updated, first_message, count in rows
    ]
