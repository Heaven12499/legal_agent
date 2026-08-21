# -*- coding: utf-8 -*-
"""
embedding 模块：把 chunk 文本转成向量，供 FAISS 建索引/检索。

模型：BAAI/bge-small-zh-v1.5（512 维），已由 scripts/download_model.py
     下载到本地 models/ 目录 —— 运行时零网络依赖，可复现。

设计要点：
    1. 单例懒加载：模型 ~95MB，进程内只加载一次；
       M3 的 agent 循环会反复检索，不能每次查询都重载模型。
    2. bge 官方检索最佳实践：查询句要加检索指令前缀，文档句不加，
       查询和文档的向量才在同一个"语义空间"里可比。
    3. normalize_embeddings=True：向量归一化后，FAISS 的内积打分
       就等于余弦相似度，语义相似度排序正确。
"""
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "bge-small-zh-v1.5"

# bge 官方推荐的检索指令：加在 query 上，doc 不加
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

_model = None


def _get_model():
    """懒加载单例。第一次调用才真正读模型，之后复用。"""
    global _model
    if _model is None:
        if not MODEL_DIR.exists():
            raise FileNotFoundError(
                f"未找到本地模型：{MODEL_DIR}\n"
                "请先运行 python scripts/download_model.py"
            )
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(str(MODEL_DIR))
    return _model


def embed_documents(texts: list) -> np.ndarray:
    """文档（chunk 文本）批量向量化，返回 (n, 512) 的 float32 数组。

    文档句不加检索指令，只做归一化。
    """
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True)


def embed_query(text: str) -> np.ndarray:
    """单条查询句向量化，返回 (512,) 的 float32 向量。

    加 bge 检索指令 + 归一化，和文档向量可比。
    """
    model = _get_model()
    vec = model.encode([QUERY_INSTRUCTION + text], normalize_embeddings=True)
    return vec[0]