# -*- coding: utf-8 -*-
"""
语料清洗脚本：原始 HTML -> 干净的法律条文纯文本

用法：
    python scripts/preprocess_corpus.py

输入：corpus/raw/labor_contract_law_raw.html  （中国人大网官方原文，抓取后原样保留）
输出：corpus/labor_contract_law.txt           （清洗后的最终语料，供切分/建索引使用）

设计要点：
    1. 纯标准库，零第三方依赖，任何环境可重跑（可复现）。
    2. 清洗目标不是"好看"，而是让下游按"第X条"正则切分时不踩坑。
    3. 结尾有对账验证：条数不等于已知的 98 条就直接报错，防止"洗坏"。
"""
import re
from pathlib import Path
from html.parser import HTMLParser

# ---------- 路径配置 ----------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_HTML = PROJECT_ROOT / "corpus" / "raw" / "labor_contract_law_raw.html"
CLEAN_TXT = PROJECT_ROOT / "corpus" / "labor_contract_law.txt"

# 法律已知条数，用于清洗后的对账验证（来源：人大网原文共 98 条）
EXPECTED_ARTICLES = 98

# 写入最终文件的来源注释，保证"可复现"（数据从哪来、什么时候抓的）
SOURCE_HEADER = """\
# 中华人民共和国劳动合同法
# 来源：中国人大网 http://www.npc.gov.cn/npc/c1773/c2518/c12898/201905/t20190523_46320.html
# 2007年6月29日通过，2008年1月1日施行，2012年12月28日修正
# 抓取日期：2026-08-20
"""


def read_text(path: Path) -> str:
    """读文件并自动探测编码。

    中文文本常见 GBK / GB2312 / UTF-8 三种编码，直接按 UTF-8 读会
    UnicodeDecodeError（docx 转出来的 txt 常是 GBK）。逐个试，能解开的算数。
    """
    for enc in ("utf-8", "gb18030"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"无法解码：{path}（尝试了 utf-8 / gb18030 均失败）")


class TextExtractor(HTMLParser):
    """HTML 去壳：剥掉 script / style / 导航，只留正文文本。

    块级元素（p/div/br/li 等）之间插入换行，保证后续"一条一行"，
    这是能被正则按行切分的前提。
    """

    def __init__(self) -> None:
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style", "head"):
            self.skip_depth += 1
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style", "head") and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def extract_body(html: str) -> list:
    """步骤 1~2：HTML 去壳 + 清理空白，输出纯文本行列表。"""
    parser = TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)

    # 折叠连续空行；去掉全角空格/制表符（网页排版常塞 　 占位）
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t\xa0　]+", "", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def slice_body(lines: list) -> list:
    """步骤 3：定位正文起止，切掉页头 / 目录 / 页脚。

    - 起点：页首的「目录」里出现过一次"第一章总则"，正文里还会再出现一次，
      所以取"第一章总则"的第二次出现作为正文起点。
    - 终点：末条是"第九十八条"，从后往前找，正文就到这里为止。
    """
    body_start, seen = None, 0
    for i, line in enumerate(lines):
        if line == "第一章总则":
            seen += 1
            if seen == 2:
                body_start = i
                break
    if body_start is None:
        raise RuntimeError("未找到正文起点，请检查原始文件是否完整")

    body_end = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith("第九十八条"):
            body_end = i + 1
            break
    if body_end is None:
        raise RuntimeError("未找到末条，请检查原始文件是否完整")

    return lines[body_start:body_end]


def validate(body: list) -> None:
    """步骤 4：对账验证——行首条号数必须等于已知条数。

    清洗最怕把正文洗丢。用正则数一遍行首的"第X条"，和已知条数对不上就报错。
    注意只数"行首"，不数文中的法条引用（如"依照本法第四十六条"），避免误计。
    """
    text = "\n".join(body)
    n = len(re.findall(r"^第[一二三四五六七八九十百零\d]+条", text, re.M))
    if n != EXPECTED_ARTICLES:
        raise RuntimeError(f"条数校验失败：期望 {EXPECTED_ARTICLES} 条，实际 {n} 条")
    print(f"[OK] 条数校验通过：{n} 条")


def main() -> None:
    print(f"[1/4] 读取原始文件：{RAW_HTML.relative_to(PROJECT_ROOT)}")
    html = read_text(RAW_HTML)

    print("[2/4] 去壳 + 清理空白 ...")
    lines = extract_body(html)

    print("[3/4] 切掉页头/目录/页脚 ...")
    body = slice_body(lines)

    print("[4/4] 对账验证 ...")
    validate(body)

    CLEAN_TXT.write_text(SOURCE_HEADER + "\n" + "\n".join(body), encoding="utf-8")
    print(f"[OK] 已生成 {CLEAN_TXT.relative_to(PROJECT_ROOT)}（{len(body)} 行）")


if __name__ == "__main__":
    main()