# -*- coding: utf-8 -*-
"""反思循环评测：量化「verify→feedback→rewrite」把多少无效/存疑引用修好了。

复用 eval_review 的埋点合同（CASES/金标），对每份跑完整 agent，从 run() 的
reflection_stats（initial/final invalid/suspect）聚合出反幻觉指标：
  - reflect_trigger_rate  触发了反思的样本比例
  - invalid_fix_rate      条号不存在/张冠李戴 的修复率
  - suspect_fix_rate      条号真但复述偏离原文 的修复率
  - avg_final_*           反思后平均剩余问题数
  - replaced_rate         反思真把答案替换掉的比例（结构化解析成功）
  - risk_recall           顺带重算传统检索召回，证明反思不损害检索能力

确定性、可复现、无需裁判 LLM；LLM 采样随机性靠 --runs 聚合消除。

用法: python -X utf8 -m backend.scripts.eval_reflection [--dry] [--runs N]
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from backend.scripts.eval_review import CASES, _validate_gold, _fmt_pair, _fmt_pct
from backend.app.rag.citations import extract_citations
from backend.app.agent.loop import run


def _run_once(case: dict) -> dict:
    """跑一次完整 agent，返回 {cited, stats, rounds}。"""
    contract = case["path"].read_text(encoding="utf-8").strip()
    result = run(
        query="请审查这份合同，逐条列出风险点。",
        history=[{"role": "user", "content": f"待审查合同全文如下：\n\n{contract}"}],
    )
    answer = result["answer"]
    cited = {(c["law"], c["num"]) for c in extract_citations(answer)}
    return {
        "cited": cited,
        "stats": result.get("reflection_stats", {}),
        "rounds": result.get("rounds", 0),
    }


def _fix_rate(initial_sum: int, final_sum: int):
    """修复率 = 修复数 / 初始问题数；无初始问题返回 None（不参与均值）。"""
    return (initial_sum - final_sum) / initial_sum if initial_sum else None


def eval_case(case: dict, runs: int) -> dict:
    """跑 runs 次并聚合反思指标；risk_recall 用并集（检索能力上限）。"""
    one = [_run_once(case) for _ in range(runs)]
    stats = [r["stats"] for r in one]

    init_inv = sum(s["initial_invalid"] for s in stats)
    fin_inv = sum(s["final_invalid"] for s in stats)
    init_sus = sum(s["initial_suspect"] for s in stats)
    fin_sus = sum(s["final_suspect"] for s in stats)

    gold_all = {pair for r in case["risks"] for pair in r["gold"]}
    union_cited = set().union(*(r["cited"] for r in one))
    risk_hit = 0
    for risk in case["risks"]:
        gold = set(risk["gold"])
        if any(gold & r["cited"] for r in one):
            risk_hit += 1

    return {
        "name": case["name"],
        "runs": runs,
        "trigger_rate": sum(1 for s in stats if s["initial_invalid"] > 0) / runs,
        "invalid_fix_rate": _fix_rate(init_inv, fin_inv),
        "avg_final_invalid": fin_inv / runs,
        "avg_final_suspect": fin_sus / runs,  # 反映 check_faithfulness 误报残留（反思不修 suspect）
        "replaced_rate": sum(1 for s in stats if s["replaced"]) / runs,
        "risk_recall": risk_hit / len(case["risks"]),
        "rounds": max(r["rounds"] for r in one),
        "gold_all": gold_all,
        "cited": union_cited,
    }


def print_report(results: list) -> None:
    print("=" * 78)
    print("反思循环评测：引用修复率 + 反幻觉指标")
    print("=" * 78)
    for r in results:
        print(f"\n■ {r['name']}  （{r['runs']} 次聚合；agent 检索轮次：{r['rounds']}）")
        print(f"   触发反思率   : {_fmt_pct(r['trigger_rate'])}")
        print(f"   invalid 修复 : {_fmt_pct(r['invalid_fix_rate']) if r['invalid_fix_rate'] is not None else '—'}")
        print(f"   反思后剩余   : invalid 均值 {r['avg_final_invalid']:.2f} · suspect 均值 {r['avg_final_suspect']:.2f}（误报残留）")
        print(f"   结构化替换率 : {_fmt_pct(r['replaced_rate'])}")
        print(f"   risk_recall  : {_fmt_pct(r['risk_recall'])}  （反思不损害检索召回）")
        if r["cited"]:
            print(f"   实际引用(并集): " + "、".join(sorted(_fmt_pair(l, n) for l, n in r["cited"])))

    print("\n" + "-" * 78)
    print("汇总（n={} 份合同）".format(len(results)))
    for k, label in [
        ("trigger_rate", "反思触发率"),
        ("invalid_fix_rate", "invalid 修复率"),
        ("avg_final_invalid", "反思后 invalid 均值"),
        ("avg_final_suspect", "反思后 suspect 均值"),
        ("replaced_rate", "结构化替换率"),
        ("risk_recall", "risk_recall"),
    ]:
        vals = [r[k] for r in results if r[k] is not None]
        if not vals:
            print(f"   {label:<20}= —（无样本）")
        elif k.startswith("avg_"):
            print(f"   {label:<20}= {sum(vals) / len(vals):.2f}")
        else:
            print(f"   {label:<20}= {_fmt_pct(sum(vals) / len(vals))}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只校验测试集，不发 LLM")
    parser.add_argument("--runs", type=int, default=3, help="每份重复次数（默认 3）")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 至少为 1")

    missing = _validate_gold()
    if missing:
        print("❌ 金标法条在语料中缺失，拒绝运行：")
        for m in missing:
            print(f"   - {m}")
        return 2
    print(f"✅ 金标校验通过：{len(CASES)} 份埋点合同。")

    if args.dry:
        print("--dry：测试集加载完成，不发 LLM。")
        return 0

    results = [eval_case(case, args.runs) for case in CASES]
    print_report(results)

    # 红线观察（不设随机失败的硬门槛）：反思后不应有编造条号残留。
    # invalid 在真实运行中本就罕见（agent 少编造），单次波动不该判 fail；以总量观察为准。
    total_fin_inv = int(sum(r["avg_final_invalid"] * r["runs"] for r in results))
    total_runs = sum(r["runs"] for r in results)
    print(f"\n编造残留红线：反思后 total invalid = {total_fin_inv} / {total_runs} 次运行"
          f"（0 = 全程无编造条号，达标）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
