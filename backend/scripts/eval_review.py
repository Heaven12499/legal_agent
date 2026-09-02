# -*- coding: utf-8 -*-
"""
M7 评测：确定性引用召回率。对每份埋点合同跑完整 agent，复用
core.citations.extract_citations 抽引用与金标比对，算 risk_recall / article_recall /
article_precision。LLM 采样有随机性，每份跑 --runs 次聚合再算。

用法: python -X utf8 -m backend.scripts.eval_review [--dry] [--runs N]
合同是输入样本可自由编写，不触碰「绝不虚构」红线。
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from backend.app.rag.citations import extract_citations, VALID
from backend.app.agent.loop import run


# 金标法条 = 语料真实存在的 (规范法名, 序数 int)。规范法名与 chunks.json 的「法律」字段一致。
SAMPLE_DIR = PROJECT_ROOT / "sample_contracts"

CASES = [
    {
        "name": "采购合同",
        "path": SAMPLE_DIR / "sample_purchase_contract.txt",
        "risks": [
            {"desc": "违约金 50% 过高", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 65)]},
            {"desc": "故意/重大过失免责条款", "gold": [("民法典（合同编）", 506)]},
            {"desc": "单方任意解除权失衡（格式条款）", "gold": [("民法典（合同编）", 496), ("民法典（合同编）", 497)]},
            {"desc": "验收期 15 日偏短", "gold": [("买卖合同解释", 12)]},
        ],
    },
    {
        "name": "租赁合同",
        "path": SAMPLE_DIR / "sample_lease_contract.txt",
        "risks": [
            {"desc": "押金一律不退（格式条款）", "gold": [("民法典（合同编）", 497)]},
            {"desc": "甲方单方免责（自然损耗/安全事故）", "gold": [("民法典（合同编）", 506)]},
            {"desc": "违约金过高（月租 24 倍）", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 65)]},
        ],
    },
    {
        "name": "技术服务合同",
        "path": SAMPLE_DIR / "sample_service_contract.txt",
        "risks": [
            # 技术服务非买卖合同，依据 585（违约金过低可请求增加）而非买卖解释 18。
            {"desc": "逾期付款利息过低（万分之零点五）", "gold": [("民法典（合同编）", 585)]},
            {"desc": "责任限制（故意/重大过失不担责）", "gold": [("民法典（合同编）", 506)]},
            {"desc": "违约金 60% 过高", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 65)]},
        ],
    },
    {
        "name": "劳动合同",
        "path": SAMPLE_DIR / "sample_labor_contract.txt",
        "risks": [
            {"desc": "试用期过长（一年期合同设六个月）", "gold": [("劳动合同法", 19)]},
            # 依据是 23（竞业限制须按月给补偿）而非 26（无效情形）。
            {"desc": "竞业限制两年且无经济补偿", "gold": [("劳动合同法", 23)]},
            # 依据是 46（应支付经济补偿情形）/87（违法解除赔偿金）而非 47（计算标准）。
            {"desc": "甲方随时解除且不支付补偿", "gold": [("劳动合同法", 46), ("劳动合同法", 87)]},
        ],
    },
    {
        "name": "软件许可及运维服务合同",
        "path": SAMPLE_DIR / "sample_software_license_contract.txt",
        "risks": [
            {"desc": "预先拟定规则允许乙方单方修改且自动生效", "gold": [("民法典（合同编）", 496), ("民法典（合同编）", 497)]},
            {"desc": "故意或重大过失导致数据损失也完全免责", "gold": [("民法典（合同编）", 506)]},
            {"desc": "高额违约金并排除司法调整", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 64)]},
            {"desc": "不可抗力免责不要求通知或证明", "gold": [("民法典（合同编）", 590)]},
        ],
    },
    {
        "name": "借款合同",
        "path": SAMPLE_DIR / "sample_loan_contract.txt",
        "risks": [
            {"desc": "约定 36% 年利率", "gold": [("民法典（合同编）", 680)]},
            {"desc": "高额违约金并排除调整", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 64)]},
            {"desc": "排除不可抗力对履约责任的影响", "gold": [("民法典（合同编）", 590)]},
        ],
    },
    {
        "name": "装修施工合同",
        "path": SAMPLE_DIR / "sample_construction_contract.txt",
        "risks": [
            {"desc": "允许整体转包或将主体结构施工交第三方", "gold": [("民法典（合同编）", 791), ("民法典（合同编）", 806)]},
            {"desc": "禁止发包人因转包、违法分包解除合同", "gold": [("民法典（合同编）", 806)]},
            {"desc": "工期或质量瑕疵即承担合同价款 40% 的违约金", "gold": [("民法典（合同编）", 585), ("合同编通则解释", 65)]},
        ],
    },
    {
        "name": "劳务派遣劳动合同",
        "path": SAMPLE_DIR / "sample_labor_dispatch_contract.txt",
        "risks": [
            {"desc": "劳务派遣劳动合同期限仅一年", "gold": [("劳动合同法", 58)]},
            {"desc": "向被派遣劳动者收取服务费且无工作期间不支付报酬", "gold": [("劳动合同法", 58), ("劳动合同法", 60)]},
            {"desc": "长期核心岗位使用劳务派遣", "gold": [("劳动合同法", 66)]},
            {"desc": "用人单位拒绝申报、缴纳社会保险", "gold": [("社会保险法", 60)]},
        ],
    },
]


def _validate_gold() -> list:
    """校验每份合同所有金标 (法名, 条号) 都真实存在于语料。返回缺失清单。"""
    missing = []
    for case in CASES:
        for risk in case["risks"]:
            for law, num in risk["gold"]:
                if law not in VALID or num not in VALID[law]:
                    missing.append(f"{case['name']} · {risk['desc']}：《{law}》第{num}条 不存在")
    return missing


def _fmt_pair(law: str, num: int) -> str:
    return f"《{law}》第{num}条"


def _run_once(case: dict) -> dict:
    """跑一次完整 agent，返回这次答案的引用集合与轮次。"""
    contract = case["path"].read_text(encoding="utf-8").strip()
    result = run(
        query="请审查这份合同，逐条列出风险点。",
        history=[{"role": "user", "content": f"待审查合同全文如下：\n\n{contract}"}],
    )
    answer = result["answer"]
    cited = {(c["law"], c["num"]) for c in extract_citations(answer)}
    return {"cited": cited, "rounds": result.get("rounds")}


def eval_case(case: dict, runs: int) -> dict:
    """跑 runs 次并聚合（单次偶发空答案不可信）：risk_recall 取各风险 hit_rate 均值，
    article_recall/precision 用并集（检索能力上限）。"""
    gold_all = {pair for risk in case["risks"] for pair in risk["gold"]}
    one = [_run_once(case) for _ in range(runs)]
    union_cited = set().union(*(r["cited"] for r in one))

    risk_detail = []
    for risk in case["risks"]:
        gold = set(risk["gold"])
        hit_runs = sum(1 for r in one if gold & r["cited"])
        risk_detail.append(
            {"desc": risk["desc"], "gold": risk["gold"], "hit_rate": hit_runs / runs}
        )

    risk_recall = sum(rd["hit_rate"] for rd in risk_detail) / len(risk_detail)
    article_recall = len(union_cited & gold_all) / len(gold_all)
    article_precision = (
        len(union_cited & gold_all) / len(union_cited) if union_cited else 0.0
    )

    return {
        "name": case["name"],
        "runs": runs,
        "risk_recall": risk_recall,
        "article_recall": article_recall,
        "article_precision": article_precision,
        "risk_detail": risk_detail,
        "cited": union_cited,
        "gold_all": gold_all,
        "rounds": max(r["rounds"] for r in one),
    }


def _fmt_pct(x: float) -> str:
    return f"{x:.0%}"


def print_report(results: list) -> None:
    print("=" * 78)
    print("M7 合同审查评测：确定性引用召回率")
    print("=" * 78)
    for r in results:
        print(f"\n■ {r['name']}  （每份跑 {r['runs']} 次聚合；agent 检索轮次：{r['rounds']}）")
        for rd in r["risk_detail"]:
            rate = rd["hit_rate"]
            mark = "✅" if rate == 1.0 else ("◐" if rate > 0 else "❌")
            gold = " / ".join(_fmt_pair(l, n) for l, n in rd["gold"])
            print(f"   {mark} {rd['desc']}  [金标: {gold}]  （命中率 {_fmt_pct(rate)}）")
        if r["cited"]:
            cited = "、".join(sorted(_fmt_pair(l, n) for l, n in r["cited"]))
            print(f"   实际引用(并集): {cited}")
        else:
            print("   实际引用(并集): （无）")
        print(
            f"   → risk_recall={_fmt_pct(r['risk_recall'])}  "
            f"article_recall={_fmt_pct(r['article_recall'])}  "
            f"article_precision={_fmt_pct(r['article_precision'])}"
        )

    print("\n" + "-" * 78)
    print("汇总（n={} 份合同）".format(len(results)))
    for k, label in [
        ("risk_recall", "risk_recall 风险点召回"),
        ("article_recall", "article_recall 法条召回"),
        ("article_precision", "article_precision 法条精确率"),
    ]:
        avg = sum(r[k] for r in results) / len(results)
        print(f"   {label:<28}= {_fmt_pct(avg)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只校验测试集，不发 LLM")
    parser.add_argument("--runs", type=int, default=3,
                        help="每份合同重复运行的次数，聚合消除 LLM 采样随机性（默认 3）")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 至少为 1")

    # 红线校验：金标必须真实存在于语料
    missing = _validate_gold()
    if missing:
        print("❌ 金标法条在语料中缺失，拒绝运行：")
        for m in missing:
            print(f"   - {m}")
        return 2

    print(f"✅ 金标校验通过：{sum(len(c['risks']) for c in CASES)} 个风险点，"
          f"{len({p for c in CASES for r in c['risks'] for p in r['gold']})} 条独立法条均在语料中。")

    if args.dry:
        print("--dry：测试集加载完成，不发 LLM。")
        return 0

    results = []
    for case in CASES:
        results.append(eval_case(case, args.runs))

    print_report(results)

    # 门槛：主指标 risk_recall 不低于 60%（M7 可复现基准，便于后续 CI）
    avg_recall = sum(r["risk_recall"] for r in results) / len(results)
    print(f"\n门槛：平均 risk_recall >= 60%  →  {_fmt_pct(avg_recall)}")
    return 0 if avg_recall >= 0.6 else 1


if __name__ == "__main__":
    sys.exit(main())
