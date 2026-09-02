# -*- coding: utf-8 -*-
"""Agent 工程化三连验收：反思循环 / 上下文压缩 / 工具注册表。
stub LLM 注入（仿 smoke_m4），不依赖真实 API。"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import backend.app.agent.llm as llm
from backend.app.agent import context, tools
from backend.app.agent.loop import run, _dispatch
from backend.app.agent.prompts import faithfulness_prompt
from backend.app.core.citations import check_faithfulness, verify_citations

from types import SimpleNamespace as NS


# ---------- stub LLM（复用 smoke_m4 的注入方式） ----------
class FakeCompletions:
    def __init__(self, script):
        self.script = script  # [("tool", q) | ("answer", text) | ("json", text), ...]
        self.i = 0

    def create(self, **kw):
        step = self.script[self.i]
        self.i += 1
        if step[0] == "tool":
            tc = NS(id=f"call_{self.i}", function=NS(name="retrieve", arguments=f'{{"query": "{step[1]}"}}'))
            return FakeResp(tool_calls=[tc])
        return FakeResp(tool_calls=None, content=step[1])


class FakeResp:
    def __init__(self, tool_calls, content=None):
        self.choices = [FakeChoice(FakeMsg(tool_calls, content))]


class FakeMsg:
    def __init__(self, tool_calls, content):
        self.tool_calls = tool_calls
        self.content = content


class FakeChoice:
    def __init__(self, msg):
        self.message = msg


def install_fake_client(script):
    class FakeClient:
        def __init__(self):
            self.chat = NS(completions=FakeCompletions(script))
    llm._instance = FakeClient()


# ---------- ① 工具注册表 ----------
def test_lookup_article():
    r = tools.lookup_article("民法典（合同编）", 585)
    assert r["found"], r
    assert "第五百八十五条" in r["text"], r["text"]
    # 别名归一：传「民法典」也能查到（normalize_law → 民法典（合同编））
    r2 = tools.lookup_article("民法典", 585)
    assert r2["found"] and "第五百八十五条" in r2["text"], r2
    # 不存在的条号 → 如实返回未找到，不崩
    r3 = tools.lookup_article("民法典（合同编）", 99999)
    assert not r3["found"] and "未找到" in r3["text"], r3
    print("[OK] lookup_article 精确查 + 别名归一 + 未找到回退")


def test_dispatch_unknown():
    r = _dispatch("nonexistent_tool", {})
    assert "未知工具" in r["text"], r
    print("[OK] _dispatch 未知工具回退错误文本")


def test_registery_driven():
    assert "retrieve" in tools.TOOL_EXECUTORS and "lookup_article" in tools.TOOL_EXECUTORS
    assert len(tools.TOOL_SCHEMAS) == 2, tools.TOOL_SCHEMAS
    print("[OK] 工具注册表：2 个 schema + 2 个执行器")


# ---------- ② 反思循环 ----------
def test_reflect_invalid():
    # 第一轮：无工具调用，直接给含不存在条号的答案 → 触发 invalid 反思
    # 反思轮：返回 JSON fixed_answer，修正引用
    install_fake_client([
        ("answer", "本合同违约金过高，依据《民法典（合同编）》第五百八十五条，且《民法典（合同编）》第九百九十九条。"),
        ("json", '{"verdict": "fix", "fixed_answer": "违约金过高，依据《民法典（合同编）》第五百八十五条，人民法院可依请求调整。"}'),
    ])
    result = run("请审查违约金条款", max_rounds=3)
    assert result["reflections"], result  # 至少反思了一轮
    assert "第九百九十九条" not in result["answer"], result["answer"]
    assert "第五百八十五条" in result["answer"], result["answer"]
    assert result["reflections"][0]["round"] == 1
    print(f"[OK] 反思循环：invalid 触发 → 修正后引用条号正确（反思 {len(result['reflections'])} 轮）")


def test_reflect_suspect_trigger():
    # 构造「条号真实但复述偏离原文」的答案：引 585 但后面跟一段无关文字
    filler = "该条规定毫无关联，此处只是一段与违约金完全无关的填充文字，用来降低与法条原文的重叠度，测试内容忠实度检测是否把它揪出来。"
    answer = "关于违约金：《民法典（合同编）》第五百八十五条。\n" + filler
    sus = check_faithfulness(answer)
    assert any(s["law"] == "民法典（合同编）" and s["num"] == 585 for s in sus), sus
    # faithfulness_prompt 反馈要包含被点名的条号
    fb = faithfulness_prompt(verify_citations(answer))
    assert "第五百八十五条" in fb, fb
    print("[OK] 反思循环：suspect（条号真但复述偏离）能被 check_faithfulness 揪出，faithfulness_prompt 点名该条")


def test_reflect_clean_noop():
    # 答案干净（无引用）→ 不触发反思，reflections 为空，不额外调 LLM
    install_fake_client([("answer", "这个问题无法直接判断，请提供合同条款。")])
    result = run("某问题", max_rounds=3)
    assert result["reflections"] == [], result
    print("[OK] 反思循环：无问题时不触发，零额外调用")


# ---------- ③ 上下文压缩 ----------
def test_context_short_unchanged():
    hist = []
    for i in range(3):
        hist += [{"role": "user", "content": f"问{i}"}, {"role": "assistant", "content": f"答{i}"}]
    out = context.build_history(hist, max_messages=16, keep_recent=8)
    assert len(out) == 6 and out == hist, out
    print("[OK] 上下文：短会话原样返回（零影响）")


def test_context_long_compresses():
    # 17 条消息 > 16 上限 → 触发摘要
    hist = []
    for i in range(8):
        hist += [{"role": "user", "content": f"问题{i}"}, {"role": "assistant", "content": f"回答{i}"}]
    hist.append({"role": "user", "content": "最后一个问题"})
    install_fake_client([("answer", "旧对话摘要：已识别违约金过高风险，依据民法典585条。")])
    out = context.build_history(hist, max_messages=16, keep_recent=8)
    # 1 条摘要 + 最近 8 条 = 9
    assert len(out) == 1 + 8, out
    assert out[0]["role"] == "system" and "对话摘要" in out[0]["content"], out[0]
    assert out[-1]["content"] == "最后一个问题", out[-1]
    print("[OK] 上下文：超长触发摘要（1 摘要 + 最近 8 条），旧轮被压缩")


def test_context_contract_excluded():
    # 合同消息不传给 build_history（api.py 单独 _history_with_contract 追加）——
    # 这里验证 build_history 只裁剪它收到的对话轮，契约由 main 组装保证
    contract = "待审查合同全文如下：\n\n" + "甲" * 500
    hist = [{"role": "user", "content": contract}]
    out = context.build_history(hist, max_messages=16, keep_recent=8)
    assert out == hist, "合同轮不被压缩（长度未超上限时原样返回）"
    print("[OK] 上下文：合同作为独立轮不被 build_history 压缩")


if __name__ == "__main__":
    test_lookup_article()
    test_dispatch_unknown()
    test_registery_driven()
    test_reflect_invalid()
    test_reflect_suspect_trigger()
    test_reflect_clean_noop()
    test_context_short_unchanged()
    test_context_long_compresses()
    test_context_contract_excluded()
    print("\n全部通过")
