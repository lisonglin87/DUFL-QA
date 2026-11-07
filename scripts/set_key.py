#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 DeepSeek API key 安全写进 .env —— key 不打印、不进聊天记录。

用法（三种，任选）：
    python scripts/set_key.py                 # 读剪贴板（先在网页上点"复制"）
    pbpaste | python scripts/set_key.py -     # 从标准输入读
    python scripts/set_key.py sk-xxxxxxxx     # 直接给参数（会进 shell 历史，不推荐）

写入后自动触发 uvicorn 热重载（touch app/config.py），不用手动重启。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
NAME = "DEEPSEEK_API_KEY"


def read_key() -> str:
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        return sys.argv[1]
    if len(sys.argv) > 1 and sys.argv[1] == "-":
        return sys.stdin.read()
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


def normalize(raw: str) -> str:
    key = "".join(raw.split())
    if len(key) == 32:          # 少了 sk- 前缀（手选复制最常见）
        key = "sk-" + key
    return key


def main() -> int:
    key = normalize(read_key())
    if not key:
        print("✗ 剪贴板是空的：先去 https://platform.deepseek.com/api_keys 点「复制」再运行")
        return 1
    if not key.startswith("sk-") or len(key) != 35:
        print(f"✗ 这不是有效的 DeepSeek key（长度 {len(key)}，应以 sk- 开头共 35 位）")
        return 1
    if not ENV.exists():
        print("✗ 找不到 .env：先运行 bash start.sh 生成一份")
        return 1

    lines = ENV.read_text(encoding="utf-8").splitlines()
    hit = False
    for i, line in enumerate(lines):
        if line.strip().startswith(NAME):
            lines[i] = f"{NAME}={key}"
            hit = True
            break
    if not hit:
        lines.append(f"{NAME}={key}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ENV.chmod(0o600)

    # 触发 uvicorn --reload（它只监听 .py）
    cfg = ROOT / "app" / "config.py"
    if cfg.exists():
        cfg.touch()

    print(f"✓ 已写入 {ENV}（{key[:3]}…{key[-4]}，长度 {len(key)}，权限 600）")
    print("✓ 已触发热重载，约 3 秒后生效；用 curl http://127.0.0.1:8000/api/health 看 has_key 是否 true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
