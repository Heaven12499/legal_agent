# -*- coding: utf-8 -*-
"""
语料清洗脚本：原始 HTML -> 干净的法律条文纯文本（配置驱动，支持多部法）

用法：
    python scripts/preprocess_corpus.py

输入：corpus/raw/*.html          （中国人大网官方原文，抓取后原样保留）
输出：corpus/*.txt               （清洗后的最终语料，供切分/建索引使用）

设计要点：
    1. 纯标准库，零第三方依赖，任何环境可重跑（可复现）。
    2. 一部法 = LAW_CONFIGS 里的一个配置项；换法/加法只改配置，不动逻辑。
    3. 清洗目标不是"好看"，而是让下游按"第X条"正则切分时不踩坑。
    4. 每部法结尾都有对账验证：条数不等于已知条数就报错，防止"洗坏"。
"""
import re
from pathlib import Path
from html.parser import HTMLParser

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------- 语料配置（每部法一项） ----------
# key        : 文件名前缀
# name       : 法律显示名（切分模块写元数据用）
# raw        : 原始 HTML 路径
# clean      : 清洗后 txt 输出路径
# expected   : 该法已知条数（对账验证用）
# last_article : 末条的条号前缀，用于从后往前定位正文终点
# source     : 写入产物的来源注释（可复现：从哪来、何时抓取）
LAW_CONFIGS = [
    {
        "key": "labor_contract_law",
        "name": "劳动合同法",
        "raw": "corpus/raw/labor_contract_law.html",
        "clean": "corpus/labor_contract_law.txt",
        "expected": 98,
        "last_article": "第九十八条",
        "source": (
            "# 中华人民共和国劳动合同法\n"
            "# 来源：中国人大网 http://www.npc.gov.cn/npc/c1773/c2518/c12898/201905/t20190523_46320.html\n"
            "# 2007年6月29日通过，2008年1月1日施行，2012年12月28日修正\n"
        ),
    },
    {
        "key": "labor_law",
        "name": "劳动法",
        "raw": "corpus/raw/labor_law.html",
        "clean": "corpus/labor_law.txt",
        "expected": 107,
        "last_article": "第一百零七条",
        "source": (
            "# 中华人民共和国劳动法（2018年修正本）\n"
            "# 来源：广东省人民政府门户网站（2018年修正本，原载中国人大网）\n"
            "#   http://www.gd.gov.cn/zwgk/wjk/zcfgk/content/mpost_2532147.html\n"
            "# 1994年7月5日通过，1995年1月1日施行，2009年第一次修正，2018年第二次修正\n"
        ),
    },
    {
        "key": "labor_dispute_arbitration_law",
        "name": "劳动争议调解仲裁法",
        "raw": "corpus/raw/labor_dispute_arbitration_law.html",
        "clean": "corpus/labor_dispute_arbitration_law.txt",
        "expected": 54,
        "last_article": "第五十四条",
        "source": (
            "# 中华人民共和国劳动争议调解仲裁法\n"
            "# 来源：中国人大网 http://www.npc.gov.cn/zgrdw/npc/zt/2008-02/23/content_1494727.htm\n"
            "# 2007年12月29日通过，2008年5月1日施行\n"
        ),
    },
    {
        "key": "labor_contract_regulation",
        "name": "劳动合同法实施条例",
        "raw": "corpus/raw/labor_contract_regulation.html",
        "clean": "corpus/labor_contract_regulation.txt",
        "expected": 38,
        "last_article": "第三十八条",
        "source": (
            "# 中华人民共和国劳动合同法实施条例\n"
            "# 来源：中国人大网 http://www.npc.gov.cn/npc/c2/c188/201905/t20190522_122802.html\n"
            "# 2008年9月3日国务院第25次常务会议通过，2008年9月18日公布，自公布之日起施行（国务院令第535号）\n"
        ),
    },
    {
        "key": "social_insurance_law",
        "name": "社会保险法",
        "raw": "corpus/raw/social_insurance_law.html",
        "clean": "corpus/social_insurance_law.txt",
        "expected": 98,
        "last_article": "第九十八条",
        "source": (
            "# 中华人民共和国社会保险法（2018年修正本）\n"
            "# 来源：中国人大网 http://www.npc.gov.cn/c2/c30834/201905/t20190521_296659.html\n"
            "# 2010年10月28日通过，2011年7月1日施行，2018年12月29日修正\n"
        ),
    },
]


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


def slice_body(lines: list, last_article: str) -> list:
    """步骤 3：定位正文起止，切掉页头 / 目录 / 页脚。

    - 起点：要兼容两种官网页面——
        带目录的页（人大网多数）：页首「目录」出现一次"第一章总则"，正文再出现一次，
            取第二次出现为正文起点；
        不带目录的页（如本条例）：只有正文开头一次，取第一次出现。
      统一写法：列出所有出现位置，>=2 次取第 2 个，否则取第 1 个。
    - 终点：末条（如"第九十八条"）从后往前找，正文就到这里为止。
    """
    occurrence = [i for i, line in enumerate(lines) if line == "第一章总则"]
    if not occurrence:
        raise RuntimeError("未找到正文起点（第一章总则），请检查原始文件是否完整")
    body_start = occurrence[1] if len(occurrence) >= 2 else occurrence[0]

    body_end = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].startswith(last_article):
            body_end = i + 1
            break
    if body_end is None:
        raise RuntimeError(f"未找到末条（{last_article}），请检查原始文件是否完整")

    return lines[body_start:body_end]


def validate(body: list, expected: int) -> None:
    """步骤 4：对账验证——行首条号数必须等于已知条数。

    清洗最怕把正文洗丢。用正则数一遍行首的"第X条"，和已知条数对不上就报错。
    注意只数"行首"，不数文中的法条引用（如"依照本法第四十六条"），避免误计。
    """
    text = "\n".join(body)
    n = len(re.findall(r"^第[一二三四五六七八九十百零\d]+条", text, re.M))
    if n != expected:
        raise RuntimeError(f"条数校验失败：期望 {expected} 条，实际 {n} 条")
    print(f"    [OK] 条数校验通过：{n} 条")


def process(cfg: dict) -> None:
    """清洗单部法：读 -> 去壳 -> 切正文 -> 对账 -> 写产物。"""
    key = cfg["key"]
    raw_path = PROJECT_ROOT / cfg["raw"]
    clean_path = PROJECT_ROOT / cfg["clean"]

    print(f"[{key}]")
    print(f"    读取原始文件：{cfg['raw']}")
    html = read_text(raw_path)

    print("    去壳 + 清理空白 ...")
    lines = extract_body(html)

    print("    切掉页头/目录/页脚 ...")
    body = slice_body(lines, cfg["last_article"])

    print("    对账验证 ...")
    validate(body, cfg["expected"])

    clean_path.write_text(cfg["source"] + "\n" + "\n".join(body), encoding="utf-8")
    print(f"    [OK] 已生成 {cfg['clean']}（{len(body)} 行）")


def main() -> None:
    print(f"共 {len(LAW_CONFIGS)} 部法待清洗\n")
    for cfg in LAW_CONFIGS:
        process(cfg)
    print("\n全部完成")


if __name__ == "__main__":
    main()