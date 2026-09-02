#!/bin/sh
set -eu

MODEL_DIR="models/bge-small-zh-v1.5"

# 语料派生产物和模型均可从版本库中的源码重建；只在首次启动时准备。
if [ ! -f corpus/chunks.json ]; then
    echo "[bootstrap] 生成法条 chunks..."
    python -m backend.app.core.chunking
fi

if [ ! -d "$MODEL_DIR" ] || [ -z "$(find "$MODEL_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    echo "[bootstrap] 下载 embedding 模型（首次启动可能需要几分钟）..."
    python -m backend.scripts.download_model
fi

# 提前构建 FAISS 索引，避免首次提问等待向量化；已有索引时跳过。
if [ ! -f corpus/chunks.faiss ]; then
    echo "[bootstrap] 构建 FAISS 索引..."
    python -c "from backend.app.core.retriever import get_retriever; get_retriever()"
fi

exec "$@"
