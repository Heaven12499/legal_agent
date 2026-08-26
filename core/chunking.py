# -*- coding: utf-8 -*-
"""
切分：法条 txt -> "一条 = 一个 chunk"（含 章/节/条号/序数/文本 元数据）。
语料清单复用 preprocess_corpus.LAW_CONFIGS，纯标准库。
"""
import json
import re
from pathlib import Path

from scripts.preprocess_corpus import LAW_CONFIGS

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------- 中文数字 -> 阿拉伯数字（条号对账用） ----------
CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def cn_num_to_int(s: str) -> int:
    """把条号里的中文数字转 int：'十九'->19，'一百零七'->107；纯数字直接返回。"""
    if s.isdigit():
        return int(s)
    total, current = 0, 0
    for ch in s:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            if current == 0:          # "十"前缺省一位，如"十九"里的"十"按 1 计
                current = 1
            total += current * CN_UNITS[ch]
            current = 0
    return total + current


# ---------- 行首特征正则：只认"行首"，不数文中的法条引用 ----------
# 与 preprocess_corpus.validate 里的口径一致："依照本法第四十六条"这种在行中，不命中
CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十百零\d]+)章")
SECTION_RE = re.compile(r"^第([一二三四五六七八九十百零\d]+)节")
ARTICLE_RE = re.compile(r"^第([一二三四五六七八九十百零\d]+)条")


def chunk_file(clean_path: Path, law_name: str, expected: int) -> list:
    """逐行扫，按行首 章/节/条 特征切分单部法；非特征行续接到上一条末尾。"""
    chunks = []
    chapter = section = None
    for line in clean_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = CHAPTER_RE.match(line)
        if m:
            chapter, section = line, None
            continue
        m = SECTION_RE.match(line)
        if m:
            section = line
            continue
        m = ARTICLE_RE.match(line)
        if m:
            chunks.append({
                "法律": law_name,
                "章": chapter,
                "节": section,
                "条号": f"第{m.group(1)}条",
                "序数": cn_num_to_int(m.group(1)),
                "文本": line,
            })
        elif chunks:
            chunks[-1]["文本"] += line
    if len(chunks) != expected:
        raise RuntimeError(f"{law_name} 切分数量校验失败：期望 {expected} 条，实际 {len(chunks)} 条")
    return chunks


def build_all() -> list:
    """切全部语料：每条法条 = 一个 chunk。"""
    all_chunks = []
    for cfg in LAW_CONFIGS:
        chunks = chunk_file(PROJECT_ROOT / cfg["clean"], cfg["name"], cfg["expected"])
        print(f"    {cfg['name']}：{len(chunks)} 条")
        all_chunks.extend(chunks)
    return all_chunks


def main() -> None:
    chunks = build_all()
    out_path = PROJECT_ROOT / "corpus" / "chunks.json"
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {len(chunks)} 个 chunk，已写入 {out_path}")


if __name__ == "__main__":
    main()