# -*- coding: utf-8 -*-
"""
检索验收脚本：M1/M2/M2.5 的可复现验收证据。

固定一组测试用例（含已知正确答案的法条 + 官方案例），一键对比
向量 / BM25 / 混合 三路，判定每条查询是否在混合 top-5 内命中目标，
输出 PASS/FAIL 汇总。

用法：
    python scripts/verify_retrieval.py

用例分两类（gold 都是检索结果的展示名，见 label()）：
    - 条文用例：gold 形如 "劳动合同法第四十七条"；
    - 案例用例：gold 形如 "指导案例183号"（label 走 案例编号）。
      案例与 395 条条文混在同一索引里（403 个 chunk），用例既验收"案例
      能被口语查询检索到"，也隐含验收"加案例不挤掉原有条文"（回归检查）。

注意：
    - 口语化弱 case（"被裁员有没有赔偿"）是**已知局限**：查询意图是"经济性
      裁员"，但语料里 41 条（经济性裁员）条文不含"裁员/赔偿"这两个词，BM25
      只能撞上含"赔偿"但语义不对路的条款（如合同被确认无效的赔偿责任），
      检索层无法命中真正该答的条文。该用例不设 gold，如实记录现状——
      真正的解法在 M3 的 LLM 查询改写。
"""
import sys
from pathlib import Path

# 把项目根目录放进 sys.path，保证从任意目录直接 python 本脚本都能 import core
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bm25 import get_bm25
from core.hybrid import get_hybrid
from core.retriever import get_retriever

# (查询, 应在混合 top-5 命中的 gold 集合, 备注)
TEST_CASES = [
    # ---------- 条文用例（M1/M2 原有，回归检查） ----------
    ("经济补偿金怎么算",
     ["劳动合同法第四十七条"],
     "经济补偿计算标准（向量/BM25 双路都该排第一）"),
    ("仲裁申请时效是多长时间",
     ["劳动争议调解仲裁法第二十七条"],
     "仲裁时效一年"),
    ("试用期是多久",
     ["劳动合同法第十九条", "劳动法第二十一条"],
     "试用期期限上限"),
    ("解除劳动合同",
     ["劳动合同法第三十七条"],
     "劳动者提前三十日通知解除（M2 混合提升案例：BM25 兜回向量漏掉的 37 条）"),
    ("被裁员有没有赔偿",
     [],
     "口语化弱 case：词表断层，不设 gold（M3 查询改写解决，如实记录）"),
    ("养老保险缴满多少年才能领",
     ["社会保险法第十六条"],
     "社保法扩库用例：累计缴费满十五年按月领取基本养老金"),
    ("没签书面劳动合同能要两倍工资吗",
     ["劳动合同法实施条例第六条"],
     "实施条例扩库用例：超一个月未签书面合同每月支付两倍工资"),
    # ---------- 案例用例（M2.5 新增，覆盖高频争议焦点） ----------
    ("离职了还能拿年终奖吗",
     ["指导案例183号"],
     "案例183号：年终奖发放前离职，非因自身过失仍应获得"),
    ("公司不缴社保，能解除合同要经济补偿吗",
     ["典型案例·朱某与某保安公司案"],
     "最高法2025典型案例：不缴社保约定无效，解除后应支付经济补偿"),
    ("签了合作协议，还能认定劳动关系吗",
     ["指导案例179号"],
     "案例179号：以'合作经营'为名掩盖用工事实，仍认定劳动关系"),
    ("平台骑手算不算公司员工",
     ["典型案例·案例1（网约货车司机）"],
     "第三批典型案例：事实优先+从属性，'合作'协议不阻却劳动关系认定"),
    ("包工头干活受伤，工伤保险谁负责",
     ["指导案例191号"],
     "案例191号：违法转包，承包单位承担工伤保险责任不以劳动关系为前提"),
]

K = 5  # 每路检索条数（与 M3 实际使用口径一致）


def label(hit: dict) -> str:
    """检索结果的展示名：条文显示'法律+条号'，案例显示'案例编号'。"""
    if hit.get("类型") == "案例":
        return hit["案例编号"]
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
        gold_set = set(gold)
        if not gold_set:
            print("  判定: 不设 gold（已知局限，如实记录）")
        elif gold_set & got:
            print(f"  判定: PASS ✅  命中 {gold_set & got}")
            n_pass += 1
        else:
            print(f"  判定: FAIL ❌  期望 {gold_set} 一个都没进 top-{K}")

    print("=" * 70)
    passed = sum(1 for _, g, _ in TEST_CASES if g)
    n_case = sum(1 for _, g, _ in TEST_CASES if g and ("指导案例" in g[0] or "典型案例" in g[0]))
    print(f"汇总: {n_pass}/{passed} 个有 gold 的用例命中（口语化弱 case 不计入，其中案例用例 {n_case} 个）")


if __name__ == "__main__":
    main()
