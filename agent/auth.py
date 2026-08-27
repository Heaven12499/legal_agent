# -*- coding: utf-8 -*-
"""用户认证核心（方案 C）：argon2 密码哈希 + PyJWT 签发/校验。

users 表与 sessions/messages 同库（data/sessions.db，SESSION_DB env 可覆盖，测试用临时库）。
JWT_SECRET：优先读 env；缺省则首次生成随机 key 并持久化到 data/.jwt_secret，
重启不失效、无需强制配 .env。token 带 user_id 与过期时间，HS256 签名。
"""
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import argon2
import jwt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_hasher = argon2.PasswordHasher()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""

_SECRET_FILE = PROJECT_ROOT / "data" / ".jwt_secret"


def _db_path() -> Path:
    env = os.environ.get("SESSION_DB")
    return Path(env) if env else PROJECT_ROOT / "data" / "sessions.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def _get_secret() -> bytes:
    """JWT 签名密钥：env 优先，否则首先生成并持久化，之后复用。"""
    env = os.environ.get("JWT_SECRET")
    if env:
        return env.encode()
    if _SECRET_FILE.exists():
        return _SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_bytes(key)
    return key


def _expire_seconds() -> int:
    return int(os.environ.get("JWT_EXPIRE_SECONDS", str(7 * 24 * 3600)))


def _hash_password(password: str) -> str:
    return _hasher.hash(password)


def _verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (argon2.exceptions.VerifyMismatchError, argon2.exceptions.InvalidHashError):
        return False


def _validate_credentials(username: str, password: str) -> None:
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(username) < 2 or len(username) > 32:
        raise ValueError("用户名长度需在 2~32 字符之间")
    if len(password) < 6:
        raise ValueError("密码长度至少 6 位")


def register_user(username: str, password: str) -> dict:
    """注册新用户，用户名冲突抛 ValueError。返回 {id, username}。"""
    username = username.strip()
    _validate_credentials(username, password)
    now = time.time()
    with closing(_connect()) as conn, conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username=?", (username,)
        ).fetchone()
        if exists:
            raise ValueError("用户名已被占用")
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES(?, ?, ?)",
            (username, _hash_password(password), now),
        )
        return {"id": cur.lastrowid, "username": username}


def authenticate(username: str, password: str) -> dict | None:
    """校验用户名/密码，成功返回 {id, username}，失败返回 None。"""
    username = username.strip()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username=?", (username,)
        ).fetchone()
    if not row or not _verify_password(row[2], password):
        return None
    return {"id": row[0], "username": row[1]}


def seed_user(username: str, password: str) -> dict:
    """幂等建初始用户：已存在则跳过，返回其记录。用于迁移旧数据 + 首次登录。"""
    username = username.strip()
    if len(password) < 6:
        raise ValueError("seed 密码长度至少 6 位")
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT id, username FROM users WHERE username=?", (username,)
        ).fetchone()
        if row:
            return {"id": row[0], "username": row[1]}
        cur = conn.execute(
            "INSERT INTO users(username, password_hash, created_at) VALUES(?, ?, ?)",
            (username, _hash_password(password), time.time()),
        )
        return {"id": cur.lastrowid, "username": username}


def create_token(user: dict) -> dict:
    """签发 JWT，返回 {token, expires_in}。"""
    now = datetime.now(timezone.utc)
    exp_sec = _expire_seconds()
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "iat": now,
        "exp": now + timedelta(seconds=exp_sec),
    }
    token = jwt.encode(payload, _get_secret(), algorithm="HS256")
    return {"token": token, "expires_in": exp_sec}


def verify_token(token: str) -> dict:
    """解析校验 JWT，返回 {id, username}；非法/过期抛 jwt.PyJWTError。"""
    payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
    return {"id": int(payload["sub"]), "username": payload["username"]}
