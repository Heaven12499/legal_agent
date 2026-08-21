# -*- coding: utf-8 -*-
"""
LLM 客户端：DeepSeek（OpenAI 兼容接口）的懒加载单例。

设计要点：
    1. 只依赖 openai SDK，走 DeepSeek 官方端点 api.deepseek.com，模型 deepseek-chat。
       base_url / key / model 全部 env 可配，换网关/换模型只改 .env 不动代码。
    2. 单例懒加载：agent 循环里每轮都要调 LLM，进程内只建一次 client。
    3. key 缺省时给出明确报错，而不是 SDK 的晦涩异常——方便一眼定位去配 .env。

env 约定（由 main.py 先把 .env 载入 os.environ，这里只读）：
    OPENAI_BASE_URL   默认 https://api.deepseek.com
    DEEPSEEK_API_KEY  必填（DeepSeek 官方 key）；兼容 OPENAI_API_KEY
    LLM_MODEL         默认 deepseek-chat
"""
import os

from openai import OpenAI

_instance = None


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
