# -*- coding: utf-8 -*-
"""
清洗民法典合同编：corpus/raw/中华人民共和国民法典_20200528.txt
→ corpus/civil_code_contract.txt（合同编条文，格式对齐现有法条库）。

民法典整部 txt 按行存放，合同编正文从"第四百六十三条"（行 1122）到
"第九百八十八条"（行 2064）。本脚本按行号切出该区间，并把条号行
（行首 4 全角空格缩进 + 条号与正文间的全角空格）清洗成现有语料格式
（行首无缩进，条号紧贴正文），以便 core.chunking 的 ARTICLE_RE 能命中。

边界口径：
- 起点：找到首行"第四百六十三条"（正文首条）
- 终点：找到"第九百八十八条"（合同编末条），其后是第四编人格权
不依赖行号（行号可能随版本变化），按条号定位更稳。

来源注释写进产物（可复现）：
    中华人民共和国民法典（2020年5月28日第十三届全国人民代表大会第三次会议通过）
    来源：国家法律法规数据库 flk.npc.gov.cn（用户提供官方 txt）
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW = PROJECT_ROOT / "corpus" / "raw" / "中华人民共和国民法典_20200528.txt"
CLEAN = PROJECT_ROOT / "corpus" / "civil_code_contract.txt"

FIRST_ARTICLE = "第四百六十三条"   # 合同编首条
LAST_ARTICLE = "第九百八十八条"     # 合同编末条（准合同末，其后是第四编人格权）
EXPECTED = 526                     # 合同编总条数（463~988，含通则/典型合同/准合同）

# 条号行：行首若干全角空格 + 条号 + 全角空格 + 正文
ARTICLE_RE = re.compile(r"^[　\s]*第[一二三四五六七八九十百零]+条")
# 章/节/分编/编标题行（同样带缩进），chunking 需要它们定位章节
SECTION_RE = re.compile(r"^[　\s]*(第[一二三四五六七八九十百零]+分编|[一二三四五六七八九十]+章|[一二三四五六七八九十]+节|[一二三四五六七八九十]+编)[　\s]")


def line_clean(line: str) -> str:
    """把 '　　　　第四百六十三条　本编调整…' 清洗成 '第四百六十三条本编调整…'。

    条号行：去行首全角空格缩进，并把条号与正文间的全角空格去掉（条号紧贴正文，
    与现有语料格式一致，供 core.chunking 的 ARTICLE_RE 命中）。
    """
    line = line.lstrip("　 ")
    m = re.match(r"(第[一二三四五六七八九十百零]+条)[　\s]*(.*)$", line)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return line


def main() -> None:
    lines = RAW.read_text(encoding="utf-8").splitlines()

    # 定位合同编正文起止（按条号，不按行号）
    start = end = None
    for i, line in enumerate(lines):
        bare = line.replace("　", "").replace(" ", "")
        if not start and FIRST_ARTICLE in bare:
            start = i
        if start and LAST_ARTICLE in bare:
            end = i
            break
    if start is None or end is None:
        raise RuntimeError(f"未定位到合同编边界（{FIRST_ARTICLE} ~ {LAST_ARTICLE}），请检查原始文件")

    body = lines[start:end + 1]
    print(f"合同编正文区间：行 {start+1} ~ {end+1}（{len(body)} 行）")

    # 清洗：条号行 line_clean；章/节/分编标题去缩进；正文续行去缩进
    out = []
    for line in body:
        if not line.strip():
            continue
        if ARTICLE_RE.match(line):
            out.append(line_clean(line))
        elif SECTION_RE.match(line):
            out.append(line.lstrip("　 "))
        else:
            out.append(line.lstrip("　 "))

    # 对账验证条数
    n = sum(1 for l in out if re.match(r"^第[一二三四五六七八九十百零]+条", l))
    if n != EXPECTED:
        raise RuntimeError(f"合同编条数校验失败：期望 {EXPECTED} 条，实际 {n} 条")
    print(f"条数校验通过：{n} 条")

    header = (
        "# 中华人民共和国民法典（合同编）\n"
        "# 来源：国家法律法规数据库 https://flk.npc.gov.cn（2020年5月28日第十三届全国人民代表大会第三次会议通过）\n"
        "# 本文件仅含合同编（第463条~第988条），用于合同审查的法条溯源；清洗自整部民法典 txt\n"
    )
    CLEAN.write_text(header + "\n" + "\n".join(out), encoding="utf-8")
    print(f"[OK] 已生成 {CLEAN}（{len(out)} 行，含 {n} 条条文）")


if __name__ == "__main__":
    main()
