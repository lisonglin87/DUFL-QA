#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索评测：用固定问题集衡量"能不能找到正确的那篇文档"。

    python scripts/eval.py              # 只测检索（不花钱，秒级）
    python scripts/eval.py --topk 6     # 换召回条数再测
    python scripts/eval.py --show 5     # 打印前 5 条失败样例，方便调参

指标：
- Recall@1：第一名就是正确文档的比例
- Recall@k：前 k 条里出现过正确文档的比例（默认 k = TOP_K）
- MRR：正确文档排名的倒数均值（越接近 1 越好）

注意：这里衡量的是**检索**，不是最终回答。回答质量还取决于模型和提示词，
所以简历里应写"检索命中率"，不要写成"回答准确率"。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import store  # noqa: E402

EVAL_FILE = ROOT / "eval" / "questions.jsonl"


def load_cases() -> list[dict]:
    cases = []
    for line in EVAL_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topk", type=int, default=0, help="覆盖召回条数，默认用 .env 的 TOP_K")
    ap.add_argument("--show", type=int, default=0, help="打印前 N 条失败样例")
    args = ap.parse_args()

    store.index.load()
    k = args.topk or store.config.TOP_K
    cases = load_cases()

    hit1 = hitk = 0
    rr = 0.0
    fails = []
    t0 = time.time()

    for c in cases:
        hits = store.index.search(c["q"], top_k=k)
        sources = [h["source"] for h in hits]
        # expect 可以是字符串，也可以是一组"同样能回答问题"的文件（避免把重复文档判成错）
        expects = c["expect"] if isinstance(c["expect"], list) else [c["expect"]]
        if sources and sources[0] in expects:
            hit1 += 1
        best = next((sources.index(e) + 1 for e in expects if e in sources), None)
        if best:
            hitk += 1
            rr += 1.0 / best
        else:
            fails.append((c["q"], " / ".join(expects), sources[:3]))

    n = len(cases)
    cost = (time.time() - t0) / max(n, 1)
    print(f"问题数 {n}   召回 k={k}")
    print(f"Recall@1  {hit1}/{n}  = {hit1/n:.1%}")
    print(f"Recall@{k}  {hitk}/{n}  = {hitk/n:.1%}")
    print(f"MRR       {rr/n:.3f}")
    print(f"平均检索耗时 {cost*1000:.0f} ms/条")

    if fails and args.show:
        print(f"\n失败样例（前 {min(args.show, len(fails))} 条）：")
        for q, exp, got in fails[: args.show]:
            print(f"  Q: {q}\n    期望: {exp}\n    实际: {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
