# -*- coding: utf-8 -*-
"""长会话上下文管理：滑动窗口 + 旧轮摘要压缩。

多轮对话 history 若全量塞给 LLM，聊久了必然超窗口、token 失控。这里把 history 压缩成
「旧轮摘要 + 最近 keep_recent 条」再交给 agent。短会话（<= max_messages）原样返回，
零影响；只对真正超长的会话触发摘要（摘要要调一次 LLM，是有成本的，尽量少触发）。
合同不受裁剪——它在 main.py 走 _history_with_contract 单独追加，不在本函数的裁剪范围。
"""
import os

from agent.llm import chat
from agent.prompts import SUMMARY_PROMPT

# env 可调；keep_recent 自动规整为偶数（保证保留的是完整 user/assistant 对）。
MAX_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "16"))
KEEP_RECENT = int(os.environ.get("KEEP_RECENT_MESSAGES", "8")) // 2 * 2
_SUMMARY_CHAR_LIMIT = 4000  # 喂给摘要的旧文本上限，防摘要请求本身超长


def build_history(history: list, max_messages: int = MAX_MESSAGES,
                  keep_recent: int = KEEP_RECENT) -> list:
    """压缩对话 history：超长则把最旧的轮次压成一条摘要，再接最近 keep_recent 条。

    返回的列表首元素是一条 {"role": "system", "content": "对话摘要：..."}（语义上是
    上下文压缩而非对话内容），其后是最近若干轮干净的 user/assistant 消息。"""
    history = list(history)
    if len(history) <= max_messages:
        return history
    keep = max(2, keep_recent)
    older, recent = history[:-keep], history[-keep:]
    summary = summarize(older)
    return [{"role": "system", "content": f"对话摘要：{summary}"}] + recent


def summarize(messages: list) -> str:
    """把一段历史对话压成一句摘要（保留风险点/结论/法条/未决问题）。"""
    text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    text = text[:_SUMMARY_CHAR_LIMIT]
    resp = chat(
        [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": text},
        ]
    )
    return (resp.choices[0].message.content or "").strip() or "（历史对话）"
