# -*- coding: utf-8 -*-
"""公开条款级评测：默认只测混合检索；--agent 才会调用 LLM。

正样本评估“关键法条是否进入 top-k”，负样本不以关键词或引用数量自动判分，
保留给人工判断模型是否误报风险。
"""
import argparse
import json
from pathlib import Path

from backend.app.core.hybrid import get_hybrid
from backend.app.core.citations import extract_citations


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = PROJECT_ROOT / "sample_contracts" / "public_clause_benchmark"


def load() -> list[dict]:
    return json.loads((DATASET_DIR / "annotations.json").read_text(encoding="utf-8"))["samples"]


def clause_text(item: dict) -> str:
    """读取一个条款点；长违约责任条款按标注的非重叠边界裁成子条款。"""
    text = (DATASET_DIR / item["text_file"]).read_text(encoding="utf-8")
    start = item.get("clause_start")
    if not start:
        return text
    begin = text.find(start)
    if begin < 0:
        raise ValueError(f"{item['id']} 未找到 clause_start: {start}")
    end_marker = item.get("clause_end")
    end = text.find(end_marker, begin + len(start)) if end_marker else -1
    if end_marker and end < 0:
        raise ValueError(f"{item['id']} 未找到 clause_end: {end_marker}")
    return text[begin:end if end >= 0 else None].strip()


def retrieval_eval(samples: list[dict], k: int) -> list[dict]:
    retriever = get_hybrid()
    rows = []
    for item in samples:
        if item["split"] != "positive":
            continue
        hits = retriever.search(item["query"], k)
        found = {(h["法律"], h["序数"]) for h in hits}
        gold = {tuple(x) for x in item["gold_articles"]}
        ranks = [rank for rank, hit in enumerate(hits, start=1)
                 if (hit["法律"], hit["序数"]) in gold]
        first_gold_rank = min(ranks) if ranks else None
        rows.append({
            "id": item["id"], "label": item["label"], "hit": bool(found & gold),
            "gold": sorted(gold), "retrieved": sorted(found),
            "first_gold_rank": first_gold_rank,
        })
    return rows


def agent_eval(samples: list[dict]) -> list[dict]:
    from backend.app.agent.loop import run

    rows = []
    for item in samples:
        if item["split"] != "positive":
            continue
        clause = clause_text(item)
        result = run(
            item["agent_prompt"],
            history=[{"role": "user", "content": f"待审查条款如下：\n\n{clause}"}],
        )
        cited = {(c["law"], c["num"]) for c in extract_citations(result["answer"])}
        gold = {tuple(x) for x in item["gold_articles"]}
        check = result.get("citation_check", {})
        rows.append({
            "id": item["id"], "hit": bool(cited & gold), "gold": sorted(gold),
            "cited": sorted(cited), "rounds": result.get("rounds"),
            "citation_invalid": len(check.get("invalid", [])),
            "citation_ungrounded": len(check.get("ungrounded", [])),
            "answer": result["answer"],
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    summary = {
        "evaluated": len(rows),
        # 这里只测“金标法条是否被引用/检索到”，不是端到端风险识别召回率。
        "gold_article_hit_rate": sum(row["hit"] for row in rows) / len(rows) if rows else 0.0,
        "hits": sum(row["hit"] for row in rows),
    }
    if rows and "first_gold_rank" in rows[0]:
        ranks = [row["first_gold_rank"] for row in rows]
        # 单金标/多金标都取首个金标的倒数排名，衡量精排是否把关键条推到前面。
        summary["mrr"] = sum(1 / rank if rank else 0 for rank in ranks) / len(rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", action="store_true", help="调用 LLM，成本与耗时更高")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    samples = load()
    retrieval = retrieval_eval(samples, args.k)
    report = {"retrieval_top_k": args.k, "retrieval": summarize(retrieval), "retrieval_rows": retrieval}
    if args.agent:
        agent = agent_eval(samples)
        report["agent"] = summarize(agent)
        report["agent_rows"] = agent
    out = DATASET_DIR / "eval_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if not k.endswith("rows")}, ensure_ascii=False, indent=2))
    print(f"完整报告：{out}")


if __name__ == "__main__":
    main()
