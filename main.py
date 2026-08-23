# -*- coding: utf-8 -*-
"""
法律 RAG 助手命令行入口：把口语问题交给 agent 循环，打印检索 trace + 带引用的答案。

用法：
    python main.py "被裁员有没有赔偿"          # 单发，打印检索 trace + 最终答案
    python main.py "被裁员有没有赔偿" --quiet  # 只打印最终答案
    python main.py --repl                      # 交互模式
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_dotenv() -> None:
    """读 .env（KEY=VALUE 行）进 os.environ，不覆盖已有环境变量。"""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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
    load_dotenv()

    args = sys.argv[1:]
    quiet = "--quiet" in args
    if "--repl" in args:
        from agent.loop import run
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
    from agent.loop import run

    result = run(query)
    if quiet:
        print(result["answer"])
    else:
        print_result(result)


if __name__ == "__main__":
    main()
