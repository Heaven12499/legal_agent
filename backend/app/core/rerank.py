# -*- coding: utf-8 -*-
"""二阶段精排：bge-reranker-base 对双路 RRF 融合后的 top-N 再打分、取 top-k。

默认关闭。设置 RERANK=1 启用；模型不可用时由上层回退。
模型只从本地 models/ 加载，下载由 bootstrap 显式完成，避免线上查询隐式联网。
"""
import os
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[3] / "models" / "bge-reranker-base"
_reranker = None


def enabled() -> bool:
    """是否启用精排：RERANK=1 显式开启。"""
    return os.environ.get("RERANK") == "1"


def get_reranker():
    """从本地加载 CrossEncoder。失败抛给上层，由上层回退。"""
    global _reranker
    if _reranker is None:
        if not MODEL_DIR.exists():
            raise FileNotFoundError(
                f"未找到本地 reranker 模型：{MODEL_DIR}；"
                "请运行 python -m backend.scripts.download_model"
            )
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(str(MODEL_DIR))
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
