# -*- coding: utf-8 -*-
"""
agent 循环：手写 while 循环实现 OpenAI function calling 多轮检索。

每轮：调 LLM -> 有工具调用就执行 retrieve 并回填 -> 直到 LLM 不再调工具、
直接给出答案。trace 记录每轮检索的 query 和命中，供调试与前端展示。
"""
import json

from agent.llm import get_client, get_model
from agent.prompts import SYSTEM_PROMPT
from agent.tools import RETRIEVE_TOOL, retrieve


def _dispatch(name: str, args: dict) -> dict:
    """执行单个工具调用，返回 {text, labels}；未知工具把错误文本喂回 LLM。"""
    if name == "retrieve":
        query = args.get("query", "")
        k = int(args.get("k", 5))
        return retrieve(query, k)
    return {"text": f"未知工具：{name}", "labels": []}


def run(query: str, history: list | None = None, max_rounds: int = 6) -> dict:
    """跑一轮 agent，返回 {"answer": str, "rounds": int, "trace": [...]}。

    history 是上一轮对话的干净 user/assistant 轮次（不含中间 tool 消息），
    拼在 system 之后、本轮 query 之前。
    """
    client, model = get_client(), get_model()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": query})
    trace = []

    for rnd in range(1, max_rounds + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[RETRIEVE_TOOL],
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # 无工具调用 => 信息已够，直接给答案
        if not msg.tool_calls:
            return {"answer": msg.content or "", "rounds": rnd, "trace": trace}

        # assistant 消息必须原样回填（含 tool_calls），API 按 tool_call_id 对齐
        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            result = _dispatch(tc.function.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result["text"]}
            )
            trace.append(
                {"round": rnd, "tool": tc.function.name, "query": args.get("query", ""),
                 "hits": result["labels"]}
            )

    # 超轮次仍无答案：返回最后已知信息
    return {"answer": "（达到最大检索轮次，仍未给出最终答案）", "rounds": max_rounds, "trace": trace}
