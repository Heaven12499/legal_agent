# -*- coding: utf-8 -*-
"""
检索验收脚本：固定一组测试用例（含已知 gold），对比向量 / BM25 / 混合三路，
判定混合 top-5 是否命中 gold，输出 PASS/FAIL 汇总。

用例覆盖两类语料（gold 为检索结果的展示名）：劳动/社保条文（如"劳动合同法第四十七条"）、
民法典合同编条文（如"民法典（合同编）第五百八十五条"）。M2.5 的官方案例已移除（M5 改为
合同审查方向，案例不再入索引）。"被裁员有没有赔偿"是已知局限、不设 gold：41 条（经济性裁员）
不含"裁员/赔偿"两词，检索层无法命中，真正的解法在 M3 的 LLM 查询改写。
"""
import sys
from pathlib import Path

# Windows 控制台默认 GBK，print ✅/❌ 会崩；固定 stdout 为 UTF-8
sys.stdout.reconfigure(encoding="utf-8")

# 把项目根目录放进 sys.path，保证从任意目录直接运行本脚本也能导入后端包。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.rag.bm25 import get_bm25
from backend.app.rag.hybrid import get_hybrid
from backend.app.rag.retriever import get_retriever

# (查询, 应在混合 top-5 命中的 gold 集合, 备注)
TEST_CASES = [
    # ---------- 劳动/社保条文用例（M1/M2 原有，回归检查） ----------
    ("经济补偿金怎么算",
     ["劳动合同法第四十七条"],
     "经济补偿计算标准（向量/BM25 双路都该排第一）"),
    ("仲裁申请时效是多长时间",
     ["劳动争议调解仲裁法第二十七条"],
     "仲裁时效一年"),
    ("试用期是多久",
     ["劳动合同法第十九条", "劳动法第二十一条"],
     "试用期期限上限（劳动合同审查也用这条）"),
    ("解除劳动合同",
     ["劳动合同法第三十七条"],
     "劳动者提前三十日通知解除（M2 混合提升：BM25 兜回向量漏掉的 37 条）"),
    ("被裁员有没有赔偿",
     [],
     "口语化弱 case：词表断层，不设 gold（M3 查询改写解决，如实记录）"),
    ("没签书面劳动合同能要两倍工资吗",
     ["劳动合同法实施条例第六条"],
     "实施条例用例：超一个月未签书面合同每月支付两倍工资"),
    # ---------- 民法典合同编用例（M5 合同审查新增，回归检查） ----------
    ("违约金太高能调低吗",
     ["民法典（合同编）第五百八十五条"],
     "违约金过分高于损失可请求减少"),
    ("格式条款不合理的免责有效吗",
     ["民法典（合同编）第四百九十七条"],
     "格式条款不合理免除/减轻责任、加重对方责任无效"),
    ("买卖合同里定金能约定多少",
     ["民法典（合同编）第五百八十六条"],
     "定金不得超过主合同标的额的20%"),
    ("故意或重大过失造成损失能免责吗",
     ["民法典（合同编）第五百零六条"],
     "故意/重大过失造成的财产损失免责条款无效"),
    ("合同解除后还能要违约金吗",
     ["民法典（合同编）第五百六十六条"],
     "合同解除不影响违约责任承担"),
    # ---------- 配套司法解释用例（M5 合同审查新增，执行口径） ----------
    ("违约金超过损失30%算过分高吗",
     ["合同编通则解释第六十五条"],
     "违约金过高认定标准：超过造成损失30%一般可认定过分高于损失"),
    ("逾期付款利息按什么算",
     ["买卖合同解释第十八条"],
     "逾期付款损失 LPR 加计30-50%"),
    ("买方多久内提出质量异议",
     [],
     "口语弱 case：质量异议→合理期限 词表断层，不设 gold（改写为「质量异议 合理期限 检验期限」可精确命中解释12条，M3 查询改写解决）"),
    ("格式条款提示义务怎么算履行",
     ["合同编通则解释第十条"],
     "格式条款提示/说明义务的认定（民法典496条的执行口径）"),
]

K = 5  # 每路检索条数（与 M3 实际使用口径一致）


def label(hit: dict) -> str:
    """检索结果的展示名：条文显示'法律+条号'，如'民法典（合同编）第五百八十五条'。"""
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
    print(f"汇总: {n_pass}/{passed} 个有 gold 的用例命中（口语化弱 case 不计入）")


if __name__ == "__main__":
    main()
