# -*- coding: utf-8 -*-
"""
agent 循环：手写 while 循环 + 工具调用，不引任何 agent 框架。

这是本项目对 LangGraph 参考实现的差异点。LangGraph 把「LLM 调用 → 工具执行 →
回填 → 再调用」封装成图/状态机；这里就是一个 ~40 行的 while 循环，每一步都显式、
可打断、可打印 trace。好处：

    1. 透明：循环里每轮调了什么工具、传了什么 query、返回了什么，trace 全记录，
       面试直接展示「被裁员 → 经济性裁员」这个改写是怎么在循环里发生的。
    2. 可控：max_rounds 硬上限防止 LLM 无限检索；工具执行失败也能把错误喂回 LLM。
    3. 零依赖：只靠 openai SDK 的 chat.completions，没有隐藏的状态管理。

循环协议（OpenAI function calling）：
    while 轮次 < max_rounds:
        resp = client.chat.completions.create(model, messages, tools=[retrieve])
        msg = resp.choices[0].message
        if msg.tool_calls:                      # LLM 要检索
            messages.append(assistant 含 tool_calls)
            for tc in msg.tool_calls:           # 执行每个 retrieve，回填 tool 结果
                result = 执行 retrieve(...)
                messages.append(tool 结果)
        else:                                    # LLM 给了最终答案
            return 答案 + trace
"""
import json

from agent.llm import get_client, get_model
from agent.prompts import SYSTEM_PROMPT
from agent.tools import RETRIEVE_TOOL, retrieve


def _dispatch(name: str, args: dict) -> dict:
    """执行单个工具调用，返回 {text, labels}。未知工具返回错误文本。"""
    if name == "retrieve":
        query = args.get("query", "")
        k = int(args.get("k", 5))
        return retrieve(query, k)
    return {"text": f"未知工具：{name}", "labels": []}


def run(query: str, max_rounds: int = 6) -> dict:
    """跑一轮 agent：口语问题 -> 改写检索 -> 带引用的答案。

    返回 {"answer": str, "rounds": int, "trace": [{round, query, hits}, ...]}
    """
    client, model = get_client(), get_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    trace = []

    for rnd in range(1, max_rounds + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[RETRIEVE_TOOL],
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # 无工具调用 -> LLM 认为信息已够，输出最终答案
        if not msg.tool_calls:
            return {"answer": msg.content or "", "rounds": rnd, "trace": trace}

        # 有工具调用 -> 把 assistant 消息（含 tool_calls）原样回填
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

        # 逐个执行工具，回填 tool 结果
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

    # 超轮次仍没给答案：返回最后已知信息，附上 trace 供排查
    return {"answer": "（达到最大检索轮次，仍未给出最终答案）", "rounds": max_rounds, "trace": trace}
