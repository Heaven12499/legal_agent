# -*- coding: utf-8 -*-
"""
agent 的工具层：retrieve 工具的 function calling schema + 执行器。

查询改写不设单独工具——检索一次不够就换法律术语再检，在 loop 循环里自然发生。
执行器直接复用 core.hybrid 的混合检索；label 口径与 verify_retrieval.py 一致。
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
    """执行一次检索，返回 {text: 给 LLM 看的文本, labels: 命中展示名（供 trace 记录）}。"""
    hits = get_hybrid().search(query, k)
    labels = [label(h) for h in hits]
    if not hits:
        text = f"检索「{query}」未命中任何条文或案例，请换一种法律表述再试。"
    else:
        text = "\n\n".join(format_chunk(h, i + 1) for i, h in enumerate(hits))
    return {"text": text, "labels": labels}
