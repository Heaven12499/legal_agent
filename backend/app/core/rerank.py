# -*- coding: utf-8 -*-
"""可选精排（P1）：bge-reranker-base 对双路 RRF 融合后的 top-N 再打分、取 top-k。

默认关闭——加载 CrossEncoder 较慢且多占显存/内存，且依赖已下载的模型。
设置环境变量 RERANK=1 启用；模型不可用（未下载/import 失败）时上层静默回退到 RRF。
"""
import os

RERANK_MODEL_NAME = "BAAI/bge-reranker-base"
_reranker = None


def enabled() -> bool:
    """是否启用精排：只看 RERANK 环境变量是否 == '1'。"""
    return os.environ.get("RERANK") == "1"


def get_reranker():
    """懒加载 CrossEncoder。import 失败会抛给上层，由上层捕获后回退。"""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANK_MODEL_NAME)
    return _reranker


def rerank(query: str, chunks: list, topk: int) -> list:
    """对 chunks（候选条文）用 reranker 打分重排，返回 topk 个（带 rerank 分数）。

    score 字段改为 reranker 分，便于与向量分区分；其余 chunk 元数据原样保留。
    """
    enc = get_reranker()
    pairs = [[query, c["文本"]] for c in chunks]
    scores = enc.predict(pairs)
    ordered = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [
        {**c, "score": round(float(s), 4), "rerank": round(float(s), 4)}
        for c, s in ordered[:topk]
    ]
