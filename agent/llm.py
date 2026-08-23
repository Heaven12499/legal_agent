# -*- coding: utf-8 -*-
"""
LLM 客户端：DeepSeek（OpenAI 兼容接口）懒加载单例 + .env 加载。
base_url / key / model 全部 env 可配，换网关换模型只改 .env。
"""
import os
from pathlib import Path

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_instance = None


def load_dotenv() -> None:
    """读 .env（KEY=VALUE 行）进 os.environ，不覆盖已有环境变量。"""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_client() -> OpenAI:
    """懒加载单例：读 env 建 OpenAI 客户端（指向 DeepSeek）。"""
    global _instance
    if _instance is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未找到 LLM API key：请把 DEEPSEEK_API_KEY 写入 .env（参考 .env.example）"
            )
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.deepseek.com")
        _instance = OpenAI(api_key=api_key, base_url=base_url)
    return _instance


def get_model() -> str:
    """读模型名（env 可配，默认 deepseek-chat）。"""
    return os.environ.get("LLM_MODEL", "deepseek-chat")


# 模块导入即加载 .env，各入口不必各自 load
load_dotenv()
