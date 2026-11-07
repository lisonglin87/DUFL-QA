#!/usr/bin/env bash
# 一键启动：首次运行会自动建虚拟环境、装依赖、生成 .env
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "▶ 创建虚拟环境…"
  python3 -m venv .venv
  echo "▶ 安装依赖（约 1-2 分钟）…"
  .venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  已生成 .env，把 DEEPSEEK_API_KEY 填进去（不填也能跑，只是走检索演示模式）"
fi

echo "▶ 启动：http://127.0.0.1:${PORT:-8000}"
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --reload
