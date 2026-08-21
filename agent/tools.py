# -*- coding: utf-8 -*-
"""
agent 的工具层：检索工具的 schema + 执行器。

只暴露一个工具 retrieve——查询改写不是单独工具，而是 agent 循环里自然发生的：
检索一次发现结果不足以回答，就换个法律术语再检索（见 loop.py 的 while 循环）。

设计要点：
    1. schema 用 OpenAI function calling 格式，description 里就把「用法律术语」讲清楚，
       引导 LLM 第一次检索就尽量法言法语，而不是塞口语词进来。
    2. 执行器直接复用 core.hybrid.get_hybrid().search()——向量+BM25+RRF 已经做好了，
       agent 层不碰检索细节，只负责把 chunk 元数据格式化成 LLM 读得懂的文本。
    3. 格式化复用 verify_retrieval.py 的 label 逻辑：条文→「法律+条号」，案例→「案例编号」，
       两处口径一致，避免一个条号两种写法。
"""
import sys
from pathlib import Path

# 保证从任意目录 python 本模块都能 import core
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.hybrid import get_hybrid

RETRIEVE_TOOL = {
    "type": "function",
    "function": {
        "name": "retrieve",
        "description": (
            "检索劳动与社会保障法律法规条文和最高人民法院/人社部官方发布的典型案例。"
            "输入一个用法律术语表达的查询（例如把口语'被裁员赔偿'改写成'经济性裁员 经济补偿'），"
            "返回最相关的条文或案例片段。一次检索结果不足以回答时，请换一种法律表述再次调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索查询，尽量用法律术语而非口语",
                },
                "k": {
                    "type": "integer",
                    "description": "返回条数，默认 5",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def label(chunk: dict) -> str:
    """chunk 的展示名：条文→「法律+条号」，案例→「案例编号」。"""
    if chunk.get("类型") == "案例":
        return chunk["案例编号"]
    return f"{chunk['法律']}{chunk['条号']}"


def format_chunk(chunk: dict, idx: int) -> str:
    """把一条检索结果格式化成给 LLM 看的一小段。"""
    return f"[{idx}] {label(chunk)}\n{chunk['文本']}"


def retrieve(query: str, k: int = 5) -> dict:
    """执行一次检索，返回 {text: 给 LLM 看的格式化文本, labels: 命中的展示名列表}。

    labels 供 loop.py 记录 trace（每轮检索命中了哪些条文/案例），面试展示「改写」过程用。
    """
    hits = get_hybrid().search(query, k)
    labels = [label(h) for h in hits]
    if not hits:
        text = f"检索「{query}」未命中任何条文或案例，请换一种法律表述再试。"
    else:
        text = "\n\n".join(format_chunk(h, i + 1) for i, h in enumerate(hits))
    return {"text": text, "labels": labels}
