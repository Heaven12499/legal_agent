# -*- coding: utf-8 -*-
"""从临时的公开合同 OCR 文本中裁出轻量、脱敏的条款级评测集。

输出每份合同 3 段（验收、付款、违约；缺失时回退保密/质保），每段约 150~900 字。
原始 OCR 全文不作为最终数据集的一部分。
"""
import json
import re
import shutil
from pathlib import Path

from backend.scripts.import_public_contracts import (
    OUT_DIR as FULL_TEXT_DIR,
    RAW_DIR,
    SOURCES,
    contains_obvious_pii,
    redact_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "sample_contracts" / "public_clause_benchmark"
TARGETS = [
    ("acceptance", ("验收", "交付")),
    ("payment", ("付款", "支付")),
    ("liability", ("违约", "解除")),
]
FALLBACKS = ("保密", "质保", "不可抗力", "争议")
ARTICLE_RE = re.compile(r"第[一二三四五六七八九十]+条")


def clean_body(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("#")).strip()


def article_sections(text: str) -> list[str]:
    positions = [m.start() for m in ARTICLE_RE.finditer(text)]
    if not positions:
        return []
    return [text[start: end].strip() for start, end in zip(positions, positions[1:] + [len(text)])]


def compact(section: str) -> str:
    section = re.sub(r"\n{2,}", "\n", section)
    section = re.sub(r"[ \t]+", "", section)
    # 句子中保留换行，方便人工核对；最长控制在 RAG 更易处理的范围。
    if len(section) > 900:
        cut = max(section.rfind("。", 300, 900), section.rfind("\n", 300, 900))
        section = section[:cut if cut > 300 else 900]
    return section.strip()


def pick_section(sections: list[str], keywords: tuple[str, ...], used: set[str]) -> str | None:
    for section in sections:
        key = section[:80]
        if key not in used and any(word in section[:140] for word in keywords):
            used.add(key)
            return compact(section)
    for section in sections:
        key = section[:80]
        if key not in used and any(word in section for word in keywords):
            used.add(key)
            return compact(section)
    return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    missing = []
    for sample_id, contract_type, source_url in SOURCES:
        source = FULL_TEXT_DIR / f"{sample_id}.txt"
        if not source.exists():
            missing.append(sample_id)
            continue
        text = clean_body(source.read_text(encoding="utf-8"))
        sections = article_sections(text)
        used: set[str] = set()
        selected = []
        for label, keywords in TARGETS:
            picked = pick_section(sections, keywords, used)
            if picked:
                selected.append((label, picked))
        for fallback in FALLBACKS:
            if len(selected) >= 3:
                break
            picked = pick_section(sections, (fallback,), used)
            if picked:
                selected.append((fallback, picked))
        if not selected:
            missing.append(sample_id)
            continue
        for index, (label, clause) in enumerate(selected, start=1):
            clause = redact_text(clause).strip()
            residual = contains_obvious_pii(clause)
            if residual:
                raise RuntimeError(f"{sample_id}/{label} 残留敏感模式：{residual}")
            name = f"{sample_id}_{index:02d}_{label}.txt"
            (OUT_DIR / name).write_text(
                "# 公开披露合同的二次脱敏条款\n"
                f"# 合同类型：{contract_type}\n"
                f"# 条款主题：{label}\n"
                "# 仅用于评测，需人工核对 OCR 文本与原公开附件。\n\n"
                f"{clause}\n",
                encoding="utf-8",
            )
            records.append({
                "id": name.removesuffix(".txt"),
                "contract_id": sample_id,
                "contract_type": contract_type,
                "topic": label,
                "source": "中国政府采购网（官方公开合同公告）",
                "source_url": source_url,
                "text_file": name,
                "characters": len(clause),
                "annotation_status": "unlabeled",
                "ocr_review_required": True,
            })
    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"samples": records, "missing_contracts": missing}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 完整 OCR 文本和原始附件不属于轻量数据集，生成条款后立即清理。
    shutil.rmtree(FULL_TEXT_DIR)
    shutil.rmtree(RAW_DIR, ignore_errors=True)
    print(f"完成：{len(records)} 条短条款，缺少合同：{missing}")


if __name__ == "__main__":
    main()
