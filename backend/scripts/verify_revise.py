# -*- coding: utf-8 -*-
"""M8 修订守卫：对每份埋点合同跑 revise_contract，断言「修改清单里没有任何一条
依据未在语料核实」——即修订不编造条号。输出核实率，有未核实即非零退出。

用法: python -X utf8 -m backend.scripts.verify_revise [--dry]
这是「绝不编造」红线在修订管线（backend.app.agent.revise）上的落地检查。
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from backend.app.agent.revise import revise_contract

SAMPLE_DIR = PROJECT_ROOT / "sample_contracts"

# 每份合同一份「审查报告」输入：列出风险点 + 语料中真实存在的依据（与 M7 金标一致）。
REVIEWS = {
    "sample_purchase_contract.txt": (
        "风险点：\n1. 违约金50%过高 → 民法典585条 + 合同编通则解释65条\n"
        "2. 故意/重大过失免责 → 民法典506条\n3. 单方任意解除权失衡格式条款 → 民法典496/497条"
    ),
    "sample_lease_contract.txt": (
        "风险点：\n1. 押金一律不退格式条款 → 民法典497条\n"
        "2. 甲方单方免责 → 民法典506条\n3. 违约金月租24倍过高 → 民法典585条 + 合同编通则解释65条"
    ),
    "sample_service_contract.txt": (
        "风险点：\n1. 逾期付款利息过低 → 民法典585条\n"
        "2. 责任限制(故意/重大过失) → 民法典506条\n3. 违约金60%过高 → 民法典585条 + 合同编通则解释65条"
    ),
    "sample_labor_contract.txt": (
        "风险点：\n1. 试用期过长 → 劳动合同法19条\n"
        "2. 竞业限制无补偿 → 劳动合同法23条\n3. 甲方随时解除不补偿 → 劳动合同法46/87条"
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="只加载测试集，不发 LLM")
    parser.add_argument("--runs", type=int, default=2,
                        help="每份合同重复跑的次数，聚合消除 LLM 采样随机性（默认 2）")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 至少为 1")

    if args.dry:
        print(f"--dry：{len(REVIEWS)} 份合同的修订守卫已加载，不发 LLM。")
        return 0

    # LLM 采样有随机性，单次可能偶发编造条号；跨 runs 聚合后，只要任何一次出现
    # 未核实依据即记一次——红线是"修订绝不编造"，一次都不允许。
    total = 0
    fabricated = 0
    for name, review in REVIEWS.items():
        contract = (SAMPLE_DIR / name).read_text(encoding="utf-8").strip()
        t = f = 0
        for _ in range(args.runs):
            r = revise_contract(contract, review)
            t += r["总数"]
            f += sum(1 for c in r["修改清单"] if not c.get("依据真实"))
        total += t
        fabricated += f
        mark = f"⚠️ 未核实 {f} 条" if f else "✅"
        print(f"{name}: {t - f}/{t} 条依据真实（{args.runs} 次聚合）  {mark}")

    print(f"\n汇总：{total} 条修改，未核实依据 {fabricated} 条")
    print("门槛：0 条未核实 →", "✅ PASS" if fabricated == 0 else "❌ FAIL")
    return 0 if fabricated == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
