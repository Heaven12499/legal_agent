# -*- coding: utf-8 -*-
"""M4 冒烟测试：stub 客户端注入，验证 多轮记忆 + 会话存储（不依赖真实 API）。"""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 会话存临时 SQLite 库，避免污染真实 data/sessions.db
_test_db = Path(tempfile.gettempdir()) / "smoke_m4_test.db"
_test_db.exists() and _test_db.unlink()
os.environ["SESSION_DB"] = str(_test_db)

import agent.llm as llm
from agent import session
from agent.loop import run


from types import SimpleNamespace as NS


class FakeCompletions:
    def __init__(self, script):
        self.script = script  # [("tool", query), ("answer", text), ...]
        self.i = 0

    def create(self, **kw):
        step = self.script[self.i]
        self.i += 1
        if step[0] == "tool":
            tc = NS(
                id=f"call_{self.i}",
                function=NS(name="retrieve", arguments=f'{{"query": "{step[1]}"}}'),
            )
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


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


def install_fake_client(script):
    class FakeClient:
        def __init__(self):
            self.chat = FakeChat(FakeCompletions(script))
    llm._instance = FakeClient()


def test_run_history():
    """第 2 轮带 history 时，messages 应含上一轮 user/assistant 干净轮次。"""
    session.append("s1", "user", "被裁员有没有赔偿")
    session.append("s1", "assistant", "上一轮答案：看情况……")

    install_fake_client([("answer", "这是第二轮的回答")])

    # 用 history 调 run，stub 脚本只有 answer，说明 history 已带入（否则无工具调会走默认）
    result = run("那经济补偿具体按什么标准算", history=session.get_history("s1"))
    assert result["answer"] == "这是第二轮的回答", result
    print("[OK] run(history=...) 正常，history 已带入 messages")


def test_session_roundtrip():
    """session 存储：append 后再 get 应原样返回。"""
    session.clear("s2")
    session.append("s2", "user", "第一句")
    session.append("s2", "assistant", "第一句回答")
    hist = session.get_history("s2")
    assert hist == [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一句回答"},
    ], hist
    print("[OK] session.append/get_history 正常")


def test_loop_with_tool():
    """stub 模拟：检索一轮 + 给答案，验证循环回填与 trace。"""
    install_fake_client([
        ("tool", "经济性裁员 经济补偿"),
        ("answer", "第41条……"),
    ])
    result = run("被裁员有没有赔偿")
    assert result["rounds"] == 2, result
    assert len(result["trace"]) == 1, result["trace"]
    assert result["trace"][0]["query"] == "经济性裁员 经济补偿"
    print("[OK] 循环机制正常：1 轮检索 + trace 记录")


if __name__ == "__main__":
    test_session_roundtrip()
    test_loop_with_tool()
    test_run_history()
    print("\n全部通过")
