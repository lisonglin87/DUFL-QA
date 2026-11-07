#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 / 增量更新知识库索引。

    python scripts/build_index.py                # 有索引就增量，没有就全量
    python scripts/build_index.py --incremental  # 只处理新增/修改/删除的文件
    python scripts/build_index.py --full         # 清空重建（改过切分参数后用这个）

增量依据 storage/manifest.json 里记录的每个文件的 mtime + 大小。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="清空重建")
    ap.add_argument("--incremental", action="store_true", help="只更新变化的文件")
    args = ap.parse_args()

    t0 = time.time()
    if args.full:
        stat = store.index.rebuild()
    elif args.incremental:
        stat = store.index.update()
    else:
        stat = store.index.update() if store.index.load() else store.index.rebuild()

    print(f"[{stat['mode']}] 文档 {stat['documents']} 篇 / 片段 {stat['chunks']} 个 "
          f"/ 向量 {'可用' if stat['vector'] else '未启用（走 BM25）'}  —— {time.time()-t0:.1f}s")
    if stat["mode"] == "incremental":
        print(f"  新增 {stat['added']}  修改 {stat['updated']}  "
              f"删除 {stat['removed']}  未变 {stat['unchanged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
