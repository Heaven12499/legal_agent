# -*- coding: utf-8 -*-
"""会话存储：SQLite 持久化（标准库 sqlite3），重启不丢。每操作开短连接（closing+事务），
天然线程安全（FastAPI 同步端点跑线程池，各线程各开各的连接）。

M9 鉴权：sessions 加 user_id 归属，所有读写按当前用户过滤——
跨用户既读不到也改不到、更删不到他人会话（合同是敏感数据，隔离是硬要求）。
"""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    contract TEXT,
    contract_name TEXT
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
_MIGRATE_CONTRACT_NAME = "ALTER TABLE sessions ADD COLUMN contract_name TEXT"
_MIGRATE_USER = "ALTER TABLE sessions ADD COLUMN user_id INTEGER"


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
    has_contract_name = any(
        r[1] == "contract_name" for r in conn.execute("PRAGMA table_info(sessions)")
    )
    if not has_contract_name:
        conn.execute(_MIGRATE_CONTRACT_NAME)
    has_user = any(
        r[1] == "user_id" for r in conn.execute("PRAGMA table_info(sessions)")
    )
    if not has_user:
        conn.execute(_MIGRATE_USER)
    return conn


def _get_owner(conn, session_id: str):
    """返回会话归属的 user_id；不存在返回 None。"""
    row = conn.execute(
        "SELECT user_id FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    return row[0] if row else None


def _check_writable(user_id: int, session_id: str, conn) -> None:
    """写会话前校验：若会话已存在且属他人，拒绝（防越权接管/写入他人会话）。

    user_id 为 None（匿名，未迁移）时允许当前用户认领——正式启动会先迁移归 seed。
    """
    owner = _get_owner(conn, session_id)
    if owner is not None and owner != user_id:
        raise ValueError("无权操作该会话")


def migrate_anonymous(user_id: int) -> int:
    """把历史未归属（user_id IS NULL）的会话迁移到指定用户。返回迁移条数。"""
    with closing(_connect()) as conn, conn:
        cur = conn.execute(
            "UPDATE sessions SET user_id=? WHERE user_id IS NULL", (user_id,)
        )
        return cur.rowcount


def save_contract(user_id: int, session_id: str, contract: str | None,
                  contract_name: str | None = None) -> None:
    """存/清会话级待审查合同：每次发送覆盖，传 None（用户移除附件）则清空。

    合同存在 sessions 表而非 messages，不占对话气泡；重新生成时据此恢复上下文。
    """
    now = time.time()
    with closing(_connect()) as conn, conn:
        _check_writable(user_id, session_id, conn)
        conn.execute(
            "INSERT INTO sessions(session_id, user_id, created_at, updated_at, contract, contract_name) "
            "VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET contract=excluded.contract, "
            "contract_name=excluded.contract_name, updated_at=excluded.updated_at",
            (session_id, user_id, now, now, contract, contract_name),
        )


def get_contract(user_id: int, session_id: str) -> str:
    """读会话当前待审查合同全文，无则空串。只读自己归属的会话。"""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT contract FROM sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()
    return (row[0] or "") if row else ""


def get_contract_meta(user_id: int, session_id: str) -> dict | None:
    """返回附件展示所需元数据，不把可能很长的合同再次传回浏览器。"""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT contract, contract_name FROM sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        ).fetchone()
    if not row or not row[0]:
        return None
    return {"name": row[1] or "已附加合同", "chars": len(row[0])}


def get_history(user_id: int, session_id: str) -> list[dict]:
    """返回该会话的对话历史（用户/助手干净轮次），无则空列表。

    只读自己归属的会话；跨用户查他人 sid 返回空（不泄露存在性）。
    每条带 id（消息自增主键），供前端"修改后重发/重新生成"时精确定位截断点。
    """
    with closing(_connect()) as conn, conn:
        rows = conn.execute(
            "SELECT id, role, content, citation FROM messages WHERE session_id=? "
            "AND session_id IN (SELECT session_id FROM sessions WHERE session_id=? AND user_id=?) "
            "ORDER BY id",
            (session_id, session_id, user_id),
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


def append(user_id: int, session_id: str, role: str, content: str, citation_check: dict | None = None) -> int:
    """追加一轮（role: user/assistant），会话不存在则创建，更新 updated_at。返回新消息 id。

    citation_check（M6 引用校验结果）以 JSON 存 citation 列，供前端展示可折叠卡片。
    ON CONFLICT 不更新 user_id，保留首建归属；越权写入由 _check_writable 拦截。
    """
    now = time.time()
    cit_json = json.dumps(citation_check, ensure_ascii=False) if citation_check else None
    with closing(_connect()) as conn, conn:
        _check_writable(user_id, session_id, conn)
        # 保留首次 created_at，只刷新 updated_at
        conn.execute(
            "INSERT INTO sessions(session_id, user_id, created_at, updated_at) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at",
            (session_id, user_id, now, now),
        )
        cur = conn.execute(
            "INSERT INTO messages(session_id, role, content, citation) VALUES(?, ?, ?, ?)",
            (session_id, role, content, cit_json),
        )
        return cur.lastrowid


def delete_from(user_id: int, session_id: str, from_id: int) -> None:
    """删除该会话 id >= from_id 的全部消息（修改重发：编辑点及其后全删，让位给新轮）。

    子查询限定自己归属的会话，跨用户越权删除不生效。
    """
    with closing(_connect()) as conn, conn:
        conn.execute(
            "DELETE FROM messages WHERE session_id=? AND id>=? AND session_id IN "
            "(SELECT session_id FROM sessions WHERE session_id=? AND user_id=?)",
            (session_id, from_id, session_id, user_id),
        )


def delete_after(user_id: int, session_id: str, after_id: int) -> None:
    """删除该会话 id > after_id 的全部消息（重新生成：删掉旧的回答，保留最后一条用户问题）。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "DELETE FROM messages WHERE session_id=? AND id>? AND session_id IN "
            "(SELECT session_id FROM sessions WHERE session_id=? AND user_id=?)",
            (session_id, after_id, session_id, user_id),
        )


def clear(user_id: int, session_id: str) -> None:
    """清空某会话（sessions + messages 两表一起删）。越权删除不生效。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "DELETE FROM messages WHERE session_id=? AND session_id IN "
            "(SELECT session_id FROM sessions WHERE session_id=? AND user_id=?)",
            (session_id, session_id, user_id),
        )
        conn.execute(
            "DELETE FROM sessions WHERE session_id=? AND user_id=?", (session_id, user_id)
        )


def list_sessions(user_id: int) -> list[dict]:
    """当前用户的所有会话摘要，按最近更新时间倒序。"""
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
            WHERE s.user_id=?
            ORDER BY s.updated_at DESC
            """,
            (user_id,),
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
