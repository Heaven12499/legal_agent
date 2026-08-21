# -*- coding: utf-8 -*-
"""
hybrid 模块：向量 + BM25 双路检索，RRF（Reciprocal Rank Fusion）融合取 top-k。

为什么是 RRF 而不是"两个分数直接加权求和"？
    向量分数是余弦相似度（0~1），BM25 分数是无界的原始分，**量纲不同、不可比**。
    直接加权要么偏心某一路，要么得先给两边做归一化（凭空引入超参数）。
    RRF 只依赖"排名"不依赖"分数"：
        fusion_score(i) = Σ_source 1 / (rrf_k + rank(source, i))
    一个 chunk 在任一单路排得靠前，融合分就高。典型 rrf_k = 60（论文常用值）。

为什么双路互补？
    - 向量检索：语义联想，"换说法"也能懂；但短口语查询时分数挤在一起、噪声混入。
    - BM25：词面精确匹配，"仲裁时效/经济补偿"一字不差就能命中；但不懂同义改写。
    两路各取所长：BM25 漏掉的说法向量能兜住，向量模糊的地方 BM25 精确术语能兜住。

用法：
    from core.hybrid import get_hybrid
    r = get_hybrid()
    for hit in r.search("被裁员有没有赔偿"):
        print(hit["法律"], hit["条号"], "向量排", hit["向量排位"], "BM25排", hit["BM25排位"])
"""
from core.bm25 import get_bm25
from core.retriever import get_retriever

_instance = None


class HybridRetriever:
    """双路融合检索器：内部持有向量检索器和 BM25 检索器。"""

    def __init__(self, vector, bm25) -> None:
        self.vector = vector
        self.bm25 = bm25

    def search(self, query: str, k: int = 5, rrf_k: int = 60, n: int = 20) -> list:
        """双路各取 n 个候选，RRF 融合后返回 top-k chunk（带各路排位）。

        参数说明：
            k     最终返回条数
            rrf_k RRF 的平滑常数（越大，融合分越"平均"，排名差距影响越小）
            n     每路候选数，要比 k 大——融合才有得选，不是拿两路 top-k 硬拼
        """
        # 双路各自的"排名表"：chunk下标 -> 该路中的排位（0 起）
        vec_rank = {i: r for r, (i, _) in enumerate(self.vector._ranked(query, n))}
        bm25_rank = {i: r for r, (i, _) in enumerate(self.bm25._ranked(query, n))}

        # RRF 融合：只有某一路命中的 chunk，融合分也只有一个加项
        fused: dict[int, float] = {}
        for i, r in vec_rank.items():
            fused[i] = 1.0 / (rrf_k + r)
        for i, r in bm25_rank.items():
            fused[i] = fused.get(i, 0.0) + 1.0 / (rrf_k + r)

        # 按融合分降序取 top-k，附上每路的排位（面试演示：看融合怎么把 doc 拉上来）
        top = sorted(fused, key=fused.get, reverse=True)[:k]
        return [
            {
                **self.vector.chunks[i],
                "score": round(fused[i], 4),
                "向量排位": vec_rank.get(i, None) + 1 if i in vec_rank else None,
                "BM25排位": bm25_rank.get(i, None) + 1 if i in bm25_rank else None,
            }
            for i in top
        ]


def get_hybrid() -> HybridRetriever:
    """懒加载单例：向量（读盘索引）和 BM25 各建一次，之后复用。"""
    global _instance
    if _instance is None:
        _instance = HybridRetriever(get_retriever(), get_bm25())
    return _instance
