# -*- coding: utf-8 -*-
"""
法律 RAG 助手命令行入口：与 web 共用 agent.loop.run，eval/测试用。

用法：
    python -m backend.app.cli "被裁员有没有赔偿"          # 单发，打印检索 trace + 最终答案
    python -m backend.app.cli "被裁员有没有赔偿" --quiet  # 只打印最终答案
    python -m backend.app.cli --repl                      # 交互模式
"""
import sys


def print_result(result: dict) -> None:
    """打印 agent 结果：先 trace，再最终答案。"""
    if result.get("trace"):
        print("─" * 60)
        print("检索 trace（LLM 每轮怎么检索 / 改写的）")
        for t in result["trace"]:
            hits = "、".join(t["hits"]) if t["hits"] else "（未命中）"
            print(f"  第{t['round']}轮 retrieve：{t['query']!r}  →  {hits}")
        print("─" * 60)
    print(result["answer"])


def main() -> None:
    args = sys.argv[1:]
    quiet = "--quiet" in args
    if "--repl" in args:
        from .agent.loop import run
        print("法律 RAG 助手（输入 exit 退出）")
        while True:
            q = input("\n> ").strip()
            if q.lower() in ("exit", "quit", "q"):
                break
            if not q:
                continue
            result = run(q)
            if quiet:
                print(result["answer"])
            else:
                print_result(result)
        return

    if not args or args[0].startswith("--"):
        print(__doc__.strip())
        return

    query = args[0]
    from .agent.loop import run

    result = run(query)
    if quiet:
        print(result["answer"])
    else:
        print_result(result)


if __name__ == "__main__":
    main()
