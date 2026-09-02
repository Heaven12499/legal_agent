# -*- coding: utf-8 -*-
"""修订版合同生成（M8）：把原合同 + M5 审查报告喂给 LLM，只改写已识别且
可给真实法条依据的风险条款，其余一字不改。输出修订全文 + 修改清单
（原条款/修订后/依据），依据逐条过 M6 校验，不核实即如实标注。
"""
import json
import re

from .llm import chat
from ..core.citations import extract_citations, VALID

REVISE_PROMPT = """你是合同修订助手。下面给你一份合同全文和针对它的审查报告（含风险点与法律依据）。

产出一份【修订版合同】和【修改说明清单】：
1. 只修改审查报告里已识别、且给出了真实法条依据的风险条款；其余条款一字不改、原样保留。
2. 每条修改都须有依据，依据只能用「《法律名》第X条」，且必须是审查报告中已检索到的真实条文，不得编造条号。
3. 某风险没有可靠法条依据就不要改，保持原文。

以严格 JSON 输出，不要任何多余文字：
{"修订版合同": "整份合同完整修订全文", "修改清单": [{"原条款": "...", "修订后": "...", "依据": "《法律名》第X条"}]}

合同全文：
"""


def _parse_json(text: str) -> dict | None:
    """尽量从 LLM 输出里取 JSON：先整体试，再剥代码围栏，最后取首个 { 到末个 }。"""
    text = text.strip()
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        candidates.append(fence.group(1))
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    if "{" in text and "}" in text:
        try:
            return json.loads(text[text.index("{"): text.rindex("}") + 1])
        except json.JSONDecodeError:
            return None
    return None


def _verify(changes: list) -> tuple[int, int]:
    """逐条对修改依据做 M6 校验：至少引了一条《法》第X条，且每条都真实存在于语料。
    返回 (有效数, 总数)——「依据里出现任何编造条号」即视为不核实。"""
    ok = 0
    for c in changes:
        cites = extract_citations(c.get("依据", ""))
        c["依据真实"] = bool(cites) and all(
            x["law"] in VALID and x["num"] in VALID[x["law"]] for x in cites
        )
        ok += int(c["依据真实"])
    return ok, len(changes)


def revise_contract(contract: str, review: str) -> dict:
    """跑修订：返回 {"修订版合同", "修改清单", "有效", "总数"}。解析失败抛 ValueError。"""
    messages = [
        {"role": "system", "content": "你只依据检索到的真实法律条文修订合同，绝不编造条号。"},
        {"role": "user", "content": REVISE_PROMPT + contract + "\n\n审查报告：\n" + review},
    ]
    resp = chat(
        messages,
        response_format={"type": "json_object"},
    )
    data = _parse_json(resp.choices[0].message.content or "")
    if not data:
        raise ValueError("修订模型未返回合法 JSON")
    changes = data.get("修改清单") or []
    ok, total = _verify(changes)
    return {
        "修订版合同": data.get("修订版合同", ""),
        "修改清单": changes,
        "有效": ok,
        "总数": total,
    }
