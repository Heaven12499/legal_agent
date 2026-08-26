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
from core.citations import verify_citations, correction_prompt, annotate


def _dispatch(name: str, args: dict) -> dict:
    """执行单个工具调用，返回 {text, labels}；未知工具把错误文本喂回 LLM。"""
    if name == "retrieve":
        query = args.get("query", "")
        k = int(args.get("k", 5))
        return retrieve(query, k)
    return {"text": f"未知工具：{name}", "labels": []}


def _finalize(client, model, messages, answer):
    """M6 引用校验：核对答案里每条「《法》第X条」是否真实存在。

    有查不到的引用 -> 喂一次纠错指令让 LLM 改用检索到的真实条文（至多 1 次），
    再校验一次；最后给答案追加校验脚注（✅ 全真 / ⚠️ 如实标注未核实项）。
    纠错失败则保留原答案，仅加脚注——绝不静默通过编造引用。
    """
    check = verify_citations(answer)
    if check["invalid"]:
        messages.append({"role": "user", "content": correction_prompt(check)})
        try:
            resp = client.chat.completions.create(model=model, messages=messages)
            fixed = (resp.choices[0].message.content or "").strip()
            if fixed:
                answer = fixed
                check = verify_citations(answer)
        except Exception:
            pass  # 纠错请求失败就保留原答案，仍会加脚注
    return annotate(answer, check), check


def run(query: str, history: list | None = None, max_rounds: int = 10) -> dict:
    """跑一轮 agent，返回 {"answer": str, "rounds": int, "trace": [...]}。

    history 是上一轮对话的干净 user/assistant 轮次（不含中间 tool 消息），
    拼在 system 之后、本轮 query 之前。
    max_rounds 是 LLM 调用轮次上限：合同审查需检索多个风险点，放宽到 10；
    问答通常 1~3 轮即结束，上限只影响最坏情况。
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

        # 无工具调用 => 信息已够，直接给答案（M6：先做引用校验再落库）
        if not msg.tool_calls:
            answer, check = _finalize(client, model, messages, msg.content or "")
            return {"answer": answer, "rounds": rnd, "trace": trace, "citation_check": check}

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
