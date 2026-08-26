# -*- coding: utf-8 -*-
"""会话存储：SQLite 持久化（标准库 sqlite3，零第三方依赖），重启不丢。

与旧内存版公开接口一致：get_history / append / clear / list_sessions。
每个操作开短连接（closing + 事务上下文），天然线程安全——
FastAPI 同步端点跑在线程池，各线程各开各的连接。
"""
import json
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
    updated_at REAL NOT NULL,
    contract TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citation TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""

# 旧库缺列：建表后幂等补列（ALTER TABLE ADD COLUMN 只执行一次）
_MIGRATE_CITATION = "ALTER TABLE messages ADD COLUMN citation TEXT"
_MIGRATE_CONTRACT = "ALTER TABLE sessions ADD COLUMN contract TEXT"


def _db_path() -> Path:
    """数据库文件：SESSION_DB 环境变量可覆盖（测试用临时库），默认 data/sessions.db。"""
    env = os.environ.get("SESSION_DB")
    return Path(env) if env else PROJECT_ROOT / "data" / "sessions.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)  # 幂等建表，每次连接保证表在
    # 旧库缺列时补上（幂等：已存在则跳过）
    has_citation = any(
        r[1] == "citation" for r in conn.execute("PRAGMA table_info(messages)")
    )
    if not has_citation:
        conn.execute(_MIGRATE_CITATION)
    has_contract = any(
        r[1] == "contract" for r in conn.execute("PRAGMA table_info(sessions)")
    )
    if not has_contract:
        conn.execute(_MIGRATE_CONTRACT)
    return conn


def save_contract(session_id: str, contract: str | None) -> None:
    """存/清会话级待审查合同：每次发送覆盖，传 None（用户移除附件）则清空。

    合同存在 sessions 表而非 messages，不占对话气泡；重新生成时据此恢复上下文。
    """
    now = time.time()
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO sessions(session_id, created_at, updated_at, contract) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET contract=excluded.contract, updated_at=excluded.updated_at",
            (session_id, now, now, contract),
        )


def get_contract(session_id: str) -> str:
    """读会话当前待审查合同全文，无则空串。"""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT contract FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    return (row[0] or "") if row else ""


def get_history(session_id: str) -> list[dict]:
    """返回该会话的对话历史（用户/助手干净轮次），无则空列表。

    每条带 id（消息自增主键），供前端"修改后重发/重新生成"时精确定位截断点。
    """
    with closing(_connect()) as conn, conn:
        rows = conn.execute(
            "SELECT id, role, content, citation FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    out = []
    for mid, r, c, cit in rows:
        m = {"id": mid, "role": r, "content": c}
        if cit:
            try:
                m["citation_check"] = json.loads(cit)
            except json.JSONDecodeError:
                pass
        out.append(m)
    return out


def append(session_id: str, role: str, content: str, citation_check: dict | None = None) -> int:
    """追加一轮（role: user/assistant），会话不存在则创建，更新 updated_at。返回新消息 id。

    citation_check（M6 引用校验结果）以 JSON 存 citation 列，供前端展示可折叠卡片。
    """
    now = time.time()
    cit_json = json.dumps(citation_check, ensure_ascii=False) if citation_check else None
    with closing(_connect()) as conn, conn:
        # 保留首次 created_at，只刷新 updated_at
        conn.execute(
            "INSERT INTO sessions(session_id, created_at, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, now, now),
        )
        cur = conn.execute(
            "INSERT INTO messages(session_id, role, content, citation) VALUES(?, ?, ?, ?)",
            (session_id, role, content, cit_json),
        )
        return cur.lastrowid


def delete_from(session_id: str, from_id: int) -> None:
    """删除该会话 id >= from_id 的全部消息（修改重发：编辑点及其后全删，让位给新轮）。"""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM messages WHERE session_id=? AND id>=?", (session_id, from_id))


def delete_after(session_id: str, after_id: int) -> None:
    """删除该会话 id > after_id 的全部消息（重新生成：删掉旧的回答，保留最后一条用户问题）。"""
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM messages WHERE session_id=? AND id>?", (session_id, after_id))


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
