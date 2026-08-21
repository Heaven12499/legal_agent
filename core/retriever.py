# -*- coding: utf-8 -*-
"""
retriever 模块：FAISS 向量检索，返回带元数据的 top-k chunk。

设计要点：
    1. IndexFlatIP + 归一化向量 => 打分就是余弦相似度（bge 推荐的做法）。
    2. 索引落盘：build() 建一次存 corpus/chunks.faiss，之后 load() 秒加载。
       向量下标与 chunks 列表下标一一对应，下标就是"主键"。
    3. 懒加载单例 get_retriever()：M3 的 agent 循环只调这一个入口，
       首次检索时建/读索引，之后复用，不重复构建。
    4. 语料只有 259 条，flat 精确检索已经足够快；不做 IVF 量化，
       理由简单：规模小，精确结果最可信，面试也最好讲。

用法：
    from core.retriever import get_retriever
    r = get_retriever()
    for hit in r.search("经济补偿金怎么算"):
        print(hit["法律"], hit["条号"], round(hit["score"], 4))
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
    def search(self, query: str, k: int = 5) -> list:
        """查询 -> top-k chunk 元数据（带 score），按相似度降序。"""
        q = embed_query(query).reshape(1, -1)
        scores, ids = self.index.search(q, k)
        return [
            {**self.chunks[i], "score": round(float(s), 4)}
            for s, i in zip(scores[0], ids[0])
            if i >= 0  # 索引条数不足 k 时，多余槽位是 -1，跳过
        ]


def get_retriever() -> Retriever:
    """懒加载单例：有落盘索引就 load，没有就 build。"""
    global _instance
    if _instance is None:
        _instance = Retriever.load() if INDEX_PATH.exists() else Retriever.build()
    return _instance