# -*- coding: utf-8 -*-
"""
切分模块：把清洗好的法条 txt 切成"一条 = 一个 chunk"，并附上元数据。
M1 之后扩展：再把 corpus/cases.json 里的官方案例合并成"案例"chunk，
两种类型混在同一个 chunks.json / 同一个索引里（M2.5 案例语料）。

M1 的第一步，也是整条 RAG 管线的数据入口。设计要点：
    1. 纯标准库（re / json），零第三方依赖，任何环境可复现。
    2. 语料清单直接复用 scripts/preprocess_corpus.py 的 LAW_CONFIGS，
       换法/加法只改那一处配置，清洗和切分用同一份清单，不重复维护。
    3. 一个 chunk = 一部法的一条完整法条（含多段续行），元数据：
       - 法律   ：哪部法（M3 回答引用、M4 引用校验都要靠它）
       - 章 / 节：条文所在章节（展示、按章过滤用）
       - 条号   ：原文写法（"第十九条"），检索结果的"第X条"标志
       - 序数   ：条号转阿拉伯数字（19），M5 评测对账用
       - 文本   ：完整条文（含条号开头）
    4. 结尾对账：切出来的条数必须等于已知条数，防止切丢。
    5. 案例 chunk 一个案例 = 一个 chunk，元数据带 类型: 案例、案例编号、
       裁判要旨、相关法条、基本案情；文本按固定模板拼装，保证可检索。

用法：
    python -m core.chunking        # 从项目根目录运行，输出 corpus/chunks.json
"""
import json
import re
from pathlib import Path

from scripts.preprocess_corpus import LAW_CONFIGS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "corpus" / "cases.json"

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
    """切分单部法：逐行扫，按行首的 章/节/条 特征归类。

    规则：
      - '#' 开头是来源注释行，跳过；
      - 命中"第X章" -> 更新当前章，旧节失效（换章必换节）；
      - 命中"第X节" -> 更新当前节；
      - 命中"第X条" -> 开一个新 chunk，把当前章/节/条号记进去；
      - 其他行       -> 是上一条的续行（多段法条的下一段），追加进上一条的文本。
    """
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


def load_case_chunks(start_index: int) -> list:
    """读 cases.json，把每个官方案例拼成一个"案例"chunk。

    一个案例 = 一个 chunk，序数从条文之后续排。文本按固定模板拼装——
    裁判要旨/争议焦点/相关法条/基本案情 都会进向量化和 BM25 分词，
    所以口语化查询有机会撞上案例里的法言法语。
    """
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    chunks = []
    for n, c in enumerate(cases, start=start_index):
        text = (
            f"【案件】{c['案例编号']} {c['案例名称']}\n"
            f"【争议焦点】{c['争议焦点']}\n"
            f"【裁判要旨】{c['裁判要旨']}\n"
            f"【相关法条】{c['相关法条']}\n"
            f"【基本案情】{c['基本案情']}"
        )
        chunks.append({
            "法律": c["法律"],
            "类型": c["类型"],
            "案例编号": c["案例编号"],
            "案例名称": c["案例名称"],
            "发布机关": c["发布机关"],
            "发布说明": c["发布说明"],
            "争议焦点": c["争议焦点"],
            "裁判要旨": c["裁判要旨"],
            "相关法条": c["相关法条"],
            "基本案情": c["基本案情"],
            "条号": c["案例编号"],   # 与条文共用"条号"字段，检索结果展示/校验统一走它
            "序数": n,
            "文本": text,
        })
    return chunks


def build_all() -> list:
    """切全部语料：条文 chunk + 案例 chunk，混在同一个列表里。"""
    all_chunks = []
    for cfg in LAW_CONFIGS:
        chunks = chunk_file(PROJECT_ROOT / cfg["clean"], cfg["name"], cfg["expected"])
        print(f"    {cfg['name']}：{len(chunks)} 条")
        all_chunks.extend(chunks)
    case_chunks = load_case_chunks(start_index=len(all_chunks))
    print(f"    官方案例：{len(case_chunks)} 条")
    all_chunks.extend(case_chunks)
    return all_chunks


def main() -> None:
    chunks = build_all()
    out_path = PROJECT_ROOT / "corpus" / "chunks.json"
    out_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    n_case = sum(1 for c in chunks if c.get("类型") == "案例")
    print(f"共 {len(chunks)} 个 chunk（含 {n_case} 个案例），已写入 {out_path}")


if __name__ == "__main__":
    main()