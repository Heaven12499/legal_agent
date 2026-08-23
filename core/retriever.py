# -*- coding: utf-8 -*-
"""
FAISS 向量检索：IndexFlatIP + 归一化向量 => 打分即余弦相似度。
索引落盘复用（向量下标即 chunk 主键），懒加载单例 get_retriever()。
"""
import json
from pathlib import Path

import faiss
import numpy as np

from core.embeddings import embed_documents, embed_query

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHUNKS_PATH = PROJECT_ROOT / "corpus" / "chunks.json"
INDEX_PATH = PROJECT_ROOT / "corpus" / "chunks.faiss"

_instance = None  # 模块级单例


class Retriever:
    """向量检索器：index 存向量，chunks 存元数据，两者按下标对齐。"""

    def __init__(self, index, chunks: list[dict]) -> None:
        self.index = index
        self.chunks = chunks

    # ---------- 构建 / 加载 ----------
    @classmethod
    def build(cls) -> "Retriever":
        """从 chunks.json 全量建索引，并落盘（只在首次跑一次）。"""
        chunks: list[dict] = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
        print(f"正在向量化 {len(chunks)} 个 chunk ...")
        vecs = embed_documents([c["文本"] for c in chunks])

        # bge-small 是 512 维；dim 从向量形状拿，不写死魔法数
        vecs = np.ascontiguousarray(vecs, dtype=np.float32)
        index = faiss.IndexFlatIP(vecs.shape[1])
        index.add(vecs)

        faiss.write_index(index, str(INDEX_PATH))
        print(f"[OK] 索引已落盘：{INDEX_PATH}")
        return cls(index=index, chunks=chunks)

    @classmethod
    def load(cls) -> "Retriever":
        """读落盘索引 + chunks 元数据，秒级启动。"""
        index = faiss.read_index(str(INDEX_PATH))
        chunks: list[dict] = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
        return cls(index=index, chunks=chunks)

    # ---------- 检索 ----------
    def _ranked(self, query: str, k: int) -> list[tuple[int, float]]:
        """内部：返回 top-k 的 (chunk下标, 向量分数)，供 RRF 融合用。"""
        q = embed_query(query).reshape(1, -1)
        scores, ids = self.index.search(q, k)
        return [
            (int(i), float(s))
            for s, i in zip(scores[0], ids[0])
            if i >= 0  # 索引条数不足 k 时，多余槽位是 -1，跳过
        ]

    def search(self, query: str, k: int = 5) -> list:
        """对外：返回 top-k chunk 元数据（带 score），按相似度降序。"""
        return [
            {**self.chunks[i], "score": round(s, 4)}
            for i, s in self._ranked(query, k)
        ]


def get_retriever() -> Retriever:
    """懒加载单例：有落盘索引就 load，没有就 build。"""
    global _instance
    if _instance is None:
        _instance = Retriever.load() if INDEX_PATH.exists() else Retriever.build()
    return _instance