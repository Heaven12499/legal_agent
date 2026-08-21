# -*- coding: utf-8 -*-
"""
下载 embedding 模型到本地 models/ 目录（可复现：任何环境跑一次即就绪）。

为什么要单独一个脚本：
    模型 ~95MB 是二进制大文件，不入库。运行时只读本地 models/，
    零网络依赖 —— 这就是"运行时可复现"（模型版本和语料一样被钉死）。

用法：
    python scripts/download_model.py

默认走国内 hf-mirror 镜像（直连 huggingface.co 不通）；要换官方源：
    HF_ENDPOINT=https://huggingface.co python scripts/download_model.py
"""
import os
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TARGET = ROOT / "models" / "bge-small-zh-v1.5"


def main() -> None:
    # 默认走镜像；用户显式设过 HF_ENDPOINT 就尊重用户的
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    if TARGET.exists() and any(TARGET.iterdir()):
        print(f"模型已存在：{TARGET}，跳过")
        return

    print(f"开始下载 {MODEL_NAME} ...")
    snapshot_download(MODEL_NAME, local_dir=str(TARGET))
    print(f"[OK] 模型已下载到 {TARGET}")


if __name__ == "__main__":
    main()