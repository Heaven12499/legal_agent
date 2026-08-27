# -*- coding: utf-8 -*-
"""手写 while 循环实现 OpenAI function calling 多轮检索：调 LLM → 有工具调用就执行
retrieve 并回填 → 直到直接给答案。trace 记录每轮 query 与命中供前端展示。"""
import json
import os

from agent.llm import chat
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_SCHEMAS, TOOL_EXECUTORS
from core.citations import verify_citations, correction_prompt, annotate

# 反思循环上限：verify→feedback→rewrite→re-verify 至多 N 轮（env 可调）。
# 与 max_rounds（检索轮预算）分开，反思不挤占检索轮。
REFLECT_MAX_ROUNDS = int(os.environ.get("REFLECT_MAX_ROUNDS", "2"))


def _dispatch(name: str, args: dict) -> dict:
    """执行单个工具调用（注册表驱动），返回 {text, labels}；未知工具把错误文本喂回 LLM。

    新增工具只需在 tools.TOOL_SCHEMAS/TOOL_EXECUTORS 注册，本函数无需改动。"""
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"text": f"未知工具：{name}", "labels": []}
    try:
        return executor(**args)
    except TypeError:
        # 参数与 schema 不符（LLM 漏传/错传）——把错误喂回 LLM，让它重试
        return {"text": f"工具 {name} 参数错误：{args}，请检查参数后重试", "labels": []}


def _strip_fence(text: str) -> str:
    """剥掉 LLM 可能加的 markdown 围栏（```json ... ```）。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.replace("```", "")
        s = s.lstrip("json").lstrip()
    return s


def _parse_reflection(content: str, fallback: str) -> tuple:
    """解析反思阶段 LLM 的 JSON 输出，返回 (答案, 是否替换)。

    LLM 偶尔不老实返回裸 JSON（带围栏或直接给文本），逐级降级解析保证不丢信息：
    只有真解析出非空 fixed_answer 才算替换；解析不出就用整段文本尽力而为。"""
    for candidate in (content, _strip_fence(content)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("fixed_answer"), str) \
                and data["fixed_answer"].strip():
            return data["fixed_answer"].strip(), True
    s = content.strip()
    return (s, True) if s else (fallback, False)


def _reflect(messages: list, answer: str) -> tuple:
    """有界反思循环：仅对「条号不存在/张冠李戴」(invalid) 触发，校验→反馈→重写→再校验，
    至多 REFLECT_MAX_ROUNDS 轮。

    刻意不把 suspect（条号真但复述偏离）纳入反思：真实运行中 agent 已很少编造（invalid 常为 0），
    而 suspect 又常是 check_faithfulness 对结构化答案（表格/列表）的误报——为它调 LLM 重写
    性价比低。suspect 只交给 annotate 如实标 ⚠️，不静默通过、也不为它烧 token。
    反思阶段用 response_format=json_object 强约束 LLM 返回 JSON，解析 fixed_answer；失败则保留。
    返回 (答案, 校验, reflections, stats)，stats 供评测量化 invalid 修复率。
    """
    check = verify_citations(answer)
    initial_invalid = len(check["invalid"])
    reflections = []
    replaced_any = False
    for k in range(1, REFLECT_MAX_ROUNDS + 1):
        if not check["invalid"]:
            break
        # DeepSeek/OpenAI 的 json_object 模式要求 prompt 里含 "json" 字样，否则不启用。
        # 显式引导 JSON 结构（含 "JSON"），correction_prompt 核心纠错文本不动。
        json_hint = (
            '请以 JSON 格式返回，字段：{"verdict": "pass" 或 "fix", '
            '"fixed_answer": "修正后的完整回答"}；不要输出 JSON 之外的任何内容。'
        )
        try:
            resp = chat(
                messages + [{"role": "user", "content": correction_prompt(check) + "\n\n" + json_hint}],
                response_format={"type": "json_object"},
            )
            new_answer, replaced = _parse_reflection(
                resp.choices[0].message.content or "", answer
            )
            if replaced:
                answer = new_answer
                replaced_any = True
            check = verify_citations(answer)
            reflections.append({
                "round": k,
                "invalid_remaining": len(check["invalid"]),
                "replaced": replaced,
            })
        except Exception:  # noqa: BLE001 —— 反思调用失败就保留当前答案，仍会 annotate
            break
    stats = {
        "rounds": len(reflections),
        "initial_invalid": initial_invalid,
        "final_invalid": len(check["invalid"]),
        "initial_suspect": len(check.get("suspect", [])),  # 不再修 suspect，仅记录/如实标注
        "final_suspect": len(check.get("suspect", [])),
        "replaced": replaced_any,
    }
    return annotate(answer, check), check, reflections, stats


def run(query: str, history: list | None = None, max_rounds: int = 10) -> dict:
    """跑一轮 agent，返回 {"answer": str, "rounds": int, "trace": [...]}。

    history 是上一轮对话的干净 user/assistant 轮次（不含中间 tool 消息），
    拼在 system 之后、本轮 query 之前。
    max_rounds 是 LLM 调用轮次上限：合同审查需检索多个风险点，放宽到 10；
    问答通常 1~3 轮即结束，上限只影响最坏情况。
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": query})
    trace = []

    for rnd in range(1, max_rounds + 1):
        resp = chat(
            messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message

        # 无工具调用 => 信息已够，直接给答案（M6 反思：校验→必要时重写→脚注）
        if not msg.tool_calls:
            answer, check, reflections, stats = _reflect(messages, msg.content or "")
            return {
                "answer": answer, "rounds": rnd, "trace": trace,
                "citation_check": check, "reflections": reflections,
                "reflection_stats": stats,
            }

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
