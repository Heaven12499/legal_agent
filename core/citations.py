# -*- coding: utf-8 -*-
"""引用校验（M6 反幻觉）：抽答案里「《法》第X条」，逐条核对是否真实存在于语料，
把编造/张冠李戴的引用如实揪出来。只核对+标注，不静默通过。「绝不编造」红线落地。"""
import json
import re
from pathlib import Path

from core.chunking import cn_num_to_int

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 法律名别名 → chunks 里的规范名（法律字段）。
# 注意：旧《合同法》的条号与民法典合同编不一一对应（旧114违约金≈民法典585），
# 故不设"合同法→合同编"同号别名——agent 写「合同法」即视为不可核实，应改引民法典。
LAW_ALIAS = {
    "民法典": "民法典（合同编）",
    "中华人民共和国民法典": "民法典（合同编）",
    "民法典合同编": "民法典（合同编）",
    "合同编": "民法典（合同编）",
    "合同编通则解释": "合同编通则解释",
    "合同编解释": "合同编通则解释",
    "通则解释": "合同编通则解释",
    "合同编通则司法解释": "合同编通则解释",
    "买卖合同解释": "买卖合同解释",
    "买卖合同司法解释": "买卖合同解释",
    "劳动合同法": "劳动合同法",
    "中华人民共和国劳动合同法": "劳动合同法",
    "劳动法": "劳动法",
    "中华人民共和国劳动法": "劳动法",
    "劳动合同法实施条例": "劳动合同法实施条例",
    "中华人民共和国劳动合同法实施条例": "劳动合同法实施条例",
    "实施条例": "劳动合同法实施条例",
    "社会保险法": "社会保险法",
    "劳动争议调解仲裁法": "劳动争议调解仲裁法",
    "调解仲裁法": "劳动争议调解仲裁法",
}

# 《法律名》第X条；条号兼容中文数字与阿拉伯数字
CITE_RE = re.compile(r"《([^》]+)》第([一二三四五六七八九十百零\d]+)条")


def _load_valid() -> dict:
    """chunks.json -> {规范法名: {序数 int, ...}}，即"真实存在"的引用全集。"""
    path = PROJECT_ROOT / "corpus" / "chunks.json"
    if not path.exists():
        raise FileNotFoundError("缺少 corpus/chunks.json，请先运行 python -m core.chunking")
    valid: dict = {}
    for ch in json.loads(path.read_text(encoding="utf-8")):
        valid.setdefault(ch["法律"], set()).add(ch["序数"])
    return valid


VALID = _load_valid()


def normalize_law(raw: str) -> str:
    """法律名别名归一：未知名保持原样（会落进 invalid，如实标注而非静默通过）。"""
    raw = raw.strip()
    return LAW_ALIAS.get(raw, raw)


def extract_citations(text: str) -> list:
    """抽出答案里所有「《法律名》第X条」，归一成 {raw_law, raw_num, num, law}。"""
    out = []
    for m in CITE_RE.finditer(text):
        raw_law = m.group(1).strip()
        raw_num = m.group(2)
        out.append({
            "raw_law": raw_law,
            "raw_num": raw_num,
            "num": cn_num_to_int(raw_num),
            "law": normalize_law(raw_law),
        })
    return out


def _dedup(cites: list) -> list:
    """按 (法名, 条号) 去重：同一法条被反复引用只计一次，保留首次出现顺序。

    total/valid/invalid 都以去重后的为准——"引用准确率"的分母是"引了哪几个不同法条"，
    而不是"引了多少次"。否则同一法条在正文 + 参考依据各出现一次会被重复计数，虚高。
    """
    seen: set = set()
    out = []
    for c in cites:
        key = (c["law"], c["num"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def verify_citations(text: str) -> dict:
    """核对一遍答案的引用：valid = 真实存在，invalid = 语料里找不到的（均已去重）。"""
    valid, invalid = [], []
    for c in _dedup(extract_citations(text)):
        if c["law"] in VALID and c["num"] in VALID[c["law"]]:
            valid.append(c)
        else:
            invalid.append(c)
    return {"total": len(valid) + len(invalid), "valid": valid, "invalid": invalid}


def correction_prompt(check: dict) -> str:
    """返回喂回 LLM 的纠错指令：把不存在的引用改成检索到的真实条文。"""
    bad = "；".join(f"《{c['raw_law']}》第{c['raw_num']}条" for c in check["invalid"])
    return (
        f"你刚才的回答中有 {len(check['invalid'])} 处法条引用在检索语料中不存在：{bad}。"
        "这些条号或法名可能被你记错或编造了。请只使用检索工具返回的真实条文重写相关引用；"
        "找不到对应条文就如实说明「未检索到直接对应的条文」，不要编造条号。"
        "只输出修正后的完整回答。"
    )


def annotate(answer: str, check: dict) -> str:
    """给答案追加一行引用校验脚注：全真打勾，有假如实标注。"""
    if not check["total"]:
        return answer  # 没引用就不动
    if not check["invalid"]:
        note = f"✅ 引用校验：{check['total']} 处引用均真实存在（来源：检索语料）"
    else:
        bad = "、".join(f"《{c['raw_law']}》第{c['raw_num']}条" for c in check["invalid"])
        note = f"⚠️ 引用校验：{len(check['invalid'])} 处未能在语料中核实——{bad}"
    return f"{answer}\n\n> {note}"
