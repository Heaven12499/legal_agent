# -*- coding: utf-8 -*-
"""
引用校验验收（M6）：用真实风格的 agent 回答片段跑 verify_citations，
确认校验器能：① 认出真引用并核对通过；② 揪出编造的条号/张冠李戴的法名；
③ 全真时追加 ✅ 脚注、有假时追加 ⚠️ 脚注；④ 同一法条重复引用只计一次（去重）。
不改答案正文。

红线：这些样例是"演示用片段"，用于测试校验器逻辑，不构成新增语料。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.citations import extract_citations, verify_citations, annotate

CASES = [
    # (说明, 回答片段, 期望 invalid 数, 期望 total=去重后条数)
    ("全真：合同编 + 通则解释",
     "依据《民法典》第585条和《合同编通则解释》第65条，违约金过高可请求减少。",
     0, 2),
    ("全真：劳动法系",
     "依据《劳动合同法》第19条，试用期不得超过2个月。",
     0, 1),
    ("编造条号：民法典第999条不存在",
     "依据《民法典》第999条，违约金过高可请求减少。",
     1, 1),
    ("张冠李戴：把劳动法条文说成民法典",
     "依据《民法典》第47条，经济补偿按工作年限计算。",
     1, 1),
    ("旧法名：合同法条号与合同编不对应，应改引民法典",
     "依据《合同法》第114条，违约金过高可请求减少。",
     1, 1),
    ("无引用：不触发校验",
     "这个问题暂时没有检索到直接对应的条文。",
     0, 0),
    ("阿拉伯数字条号：第585条",
     "依据《民法典》第585条规定。",
     0, 1),
    # 仿真例：正文 + 参考依据 各引一次《劳动合同法》第4条，再加第30条
    # 去重后应只计 2 个法条（第4条只算一次），而非 3 处。
    ("去重：同一法条正文+依据各引一次只计一",
     "依据《劳动合同法》第4条（民主程序）及《劳动合同法》第4条的公示要求，"
     "并依《劳动合同法》第30条及时足额支付。",
     0, 2),
]

fail = 0
for i, (note, text, exp_invalid, exp_total) in enumerate(CASES, 1):
    check = verify_citations(text)
    got_invalid = len(check["invalid"])
    got_total = check["total"]
    ok = got_invalid == exp_invalid and got_total == exp_total
    if not ok:
        fail += 1
    tag = "PASS ✅" if ok else "FAIL ❌"
    cites = extract_citations(text)
    detail = "; ".join(f"{c['law']} {c['num']}" for c in cites) or "（无引用）"
    print(f"{i}. {note}")
    print(f"   提取(含重复): {detail}")
    print(f"   total={got_total} 期望={exp_total} | invalid={got_invalid} 期望={exp_invalid}  {tag}")
    print(f"   脚注: {annotate(text, check).splitlines()[-1]}")
    print()

if fail:
    print(f"=== {fail} 项未过，请检查 ===")
    sys.exit(1)

# 证据白名单：法条即便存在于语料，只要不是本轮 retrieve / lookup_article 返回的结果，
# 也必须被标成 ungrounded，不能冒充本轮 RAG 证据。
grounded = verify_citations(
    "依据《民法典》第585条，违约金过高可请求调整。",
    {("民法典（合同编）", 585)},
)
ungrounded = verify_citations(
    "依据《民法典》第586条，定金不得超过主合同标的额的百分之二十。",
    {("民法典（合同编）", 585)},
)
if grounded["ungrounded"] or len(ungrounded["ungrounded"]) != 1:
    print("=== 证据白名单校验未通过，请检查 ===")
    sys.exit(1)
print("[OK] 证据白名单：只允许本轮检索到的法条被引用")
print("=== 全部通过 = 校验器可用，可安全接入 agent loop ===")
