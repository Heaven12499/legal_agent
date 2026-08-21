# -*- coding: utf-8 -*-
"""
法律 RAG 助手命令行入口（M3）。

把口语问题交给手写 agent 循环：LLM 先改写查询，再反复检索，最后给带条号引用的答案。

用法：
    python main.py "被裁员有没有赔偿"          # 单发，打印检索 trace + 最终答案
    python main.py "被裁员有没有赔偿" --quiet  # 只打印最终答案
    python main.py --repl                      # 交互模式（每条问题一行）

首次运行前：把 .env.example 复制为 .env 并填入 DEEPSEEK_API_KEY。
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_dotenv() -> None:
    """极简 .env 加载：读 KEY=VALUE 行进 os.environ，不覆盖已有环境变量。

    手写 ~15 行，不引 python-dotenv——和 preprocess/chunking 一样保持零第三方依赖。
    """
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
    """打印 agent 结果：先 trace（展示改写过程），再最终答案。"""
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
