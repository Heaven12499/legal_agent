# -*- coding: utf-8 -*-
"""
检索验收脚本：M1/M2 的可复现验收证据。

固定一组测试用例（含已知正确答案的法条），一键对比 向量 / BM25 / 混合 三路，
判定每条查询是否在混合 top-5 内命中目标条文，输出 PASS/FAIL 汇总。

用法：
    python scripts/verify_retrieval.py

注意：
    - 口语化弱 case（"被裁员有没有赔偿"）是**已知局限**：语料里 46/47 条
      不含"裁员/赔偿"这两个词，词表断层，检索层无法命中。计划在 M3 用
      LLM 查询改写解决，故该用例不设 gold，用于如实记录现状。
"""
import sys
from pathlib import Path

# 把项目根目录放进 sys.path，保证从任意目录直接 python 本脚本都能 import core
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bm25 import get_bm25
from core.hybrid import get_hybrid
from core.retriever import get_retriever

# (查询, 应在混合 top-5 命中的 [(法律, 条号), ...], 备注)
TEST_CASES = [
    ("经济补偿金怎么算",
     [("劳动合同法", "第四十七条")],
     "经济补偿计算标准（向量/BM25 双路都该排第一）"),
    ("仲裁申请时效是多长时间",
     [("劳动争议调解仲裁法", "第二十七条")],
     "仲裁时效一年"),
    ("试用期是多久",
     [("劳动合同法", "第十九条"), ("劳动法", "第二十一条")],
     "试用期期限上限"),
    ("解除劳动合同",
     [("劳动合同法", "第三十七条")],
     "劳动者提前三十日通知解除（M2 混合提升案例：BM25 兜回向量漏掉的 37 条）"),
    ("被裁员有没有赔偿",
     [],
     "口语化弱 case：词表断层，检索层已知无法命中，M3 查询改写解决"),
    ("养老保险缴满多少年才能领",
     [("社会保险法", "第十六条")],
     "社保法扩库用例：累计缴费满十五年按月领取基本养老金"),
    ("没签书面劳动合同能要两倍工资吗",
     [("劳动合同法实施条例", "第六条")],
     "实施条例扩库用例：超一个月未签书面合同每月支付两倍工资"),
]

K = 5  # 每路检索条数（与 M3 实际使用口径一致）


def label(hit: dict) -> str:
    return f"{hit['法律']}{hit['条号']}"


def show(tag: str, hits: list) -> str:
    return f"  {tag:5s}: " + " | ".join(label(h) for h in hits)


def main() -> None:
    vec, bm, hyb = get_retriever(), get_bm25(), get_hybrid()
    n_pass = 0
    for query, gold, note in TEST_CASES:
        print("=" * 70)
        print(f"QUERY: {query}   （{note}）")
        print(show("向量", vec.search(query, K)))
        print(show("BM25", bm.search(query, K)))
        print(show("混合", hyb.search(query, K)))

        got = {label(h) for h in hyb.search(query, K)}
        gold_set = {f"{law}{art}" for law, art in gold}
        if not gold_set:
            print("  判定: 不设 gold（已知局限，如实记录）")
        elif gold_set & got:
            print(f"  判定: PASS ✅  命中 {gold_set & got}")
            n_pass += 1
        else:
            print(f"  判定: FAIL ❌  期望 {gold_set} 一个都没进 top-{K}")

    print("=" * 70)
    passed = sum(1 for _, g, _ in TEST_CASES if g)
    print(f"汇总: {n_pass}/{passed} 个有 gold 的用例命中（口语化弱 case 不计入）")


if __name__ == "__main__":
    main()
