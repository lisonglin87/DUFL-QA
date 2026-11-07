#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目搬家后跑一次：修好 .venv 里写死的绝对路径。

    python scripts/fix_paths.py

背景：虚拟环境里的 pip / uvicorn 等入口脚本，第一行 shebang 写的是
"创建时"的绝对路径。文件夹一改名或一移动，这些命令就会报
"No such file or directory"。这个脚本把 shebang 改到当前位置。

注意：修完要重启正在跑的服务——进程的工作目录不会跟着文件走。
直接 `bash start.sh` 启动的不用管，它每次都会 cd 到自己所在目录。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / ".venv" / "bin"
PYTHON = BIN / "python"


def main() -> int:
    if not BIN.exists():
        print("✗ 没有找到 .venv，直接运行 bash start.sh 会自动重建")
        return 1

    fixed, scanned = 0, 0
    for path in BIN.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        if not text.startswith("#!"):
            continue
        scanned += 1
        first, sep, rest = text.partition("\n")
        if str(PYTHON) in first:
            continue
        if "/.venv/bin/python" in first:          # 指向别处的旧路径
            path.write_text(f"#!{PYTHON}\n{rest}")
            fixed += 1

    print(f"✓ 检查 {scanned} 个脚本，修正 {fixed} 个 shebang → {PYTHON}")
    if fixed:
        print("→ 记得重启正在运行的服务（Ctrl+C 后 bash start.sh）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
