# -*- coding: utf-8 -*-
"""对已裁剪的公开合同条款执行更严格的二次脱敏和残留检查。"""
import re
from pathlib import Path

from backend.scripts.import_public_contracts import contains_obvious_pii, redact_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = PROJECT_ROOT / "sample_contracts" / "public_clause_benchmark"


def split_header(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    header = []
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        header.append(lines.pop(0))
    return "\n".join(header).strip(), "\n".join(lines)


def main() -> None:
    forbidden = ("北京市东城区", "中技国际", "中电科金仓", "北京东方通", "华胜天成")
    for path in sorted(BENCHMARK_DIR.glob("*.txt")):
        header, body = split_header(path.read_text(encoding="utf-8"))
        body = redact_text(body).strip()
        residual = contains_obvious_pii(body)
        leaked = [value for value in forbidden if value in body]
        if residual or leaked:
            raise RuntimeError(f"{path.name} 残留：{residual + leaked}")
        path.write_text(f"{header}\n\n{body}\n", encoding="utf-8")
    print(f"[OK] 已清洗 {len(list(BENCHMARK_DIR.glob('*.txt')))} 条文本")


if __name__ == "__main__":
    main()
