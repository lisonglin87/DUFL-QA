# -*- coding: utf-8 -*-
"""FastAPI 入口：对话（SSE 流式）、重建索引、健康检查、单页前端。"""
from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, prompt, store

app = FastAPI(title="校园智能问答助手", version="0.2.0")

# 允许从任意本地来源调用（file:// 打开、其他端口预览都能用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ASSETS = config.BASE_DIR / "web" / "assets"
if ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS)), name="assets")


# ------------------------- 数据结构 -------------------------
class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[Turn] = []


# ------------------------- 工具 -------------------------
def ensure_index():
    """首次请求时自动加载/构建索引，省掉手动初始化那一步。"""
    if not store.index.chunks:
        if not store.index.load():
            try:
                store.index.rebuild()
            except Exception as exc:
                print(f"[warn] 建索引失败：{exc}")


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _demo_answer(hits: list[dict]) -> str:
    """没有 API key 时的检索演示，方便先看通链路。"""
    lines = ["**当前是检索演示模式**（没有配置 DEEPSEEK_API_KEY，所以没有调用大模型）。\n",
             "我在资料库里找到了这些片段：\n"]
    for i, h in enumerate(hits, start=1):
        snippet = h["text"].replace("\n", " ")[:90]
        lines.append(f"**{i}. {h['source']}**（融合分 {h['score']}）\n{snippet}…\n")
    lines.append("填好 `.env` 里的 key 重启服务，这里就会变成模型生成的回答。")
    return "\n".join(lines)


async def _stream_text(text: str, size: int = 18):
    """把固定文本切片吐出，前端体感和真流式一致。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]
        await asyncio.sleep(0.02)


# ------------------------- 路由 -------------------------
@app.get("/")
def home():
    return FileResponse(config.BASE_DIR / "web" / "index.html")


@app.get("/api/health")
def health():
    ensure_index()
    return {
        "ok": True,
        "model": config.MODEL,
        "has_key": config.HAS_KEY,
        "vector": store.index.vector_ok,
        "embed": config.EMBED_PROVIDER,
        "chunks": len(store.index.chunks),
        "top_k": config.TOP_K,
    }


@app.post("/api/rebuild")
def rebuild(mode: str = "incremental"):
    """mode=incremental 只更新变化的文件；mode=full 整库重建。"""
    try:
        stat = store.index.update() if mode != "full" else store.index.rebuild()
        return {"ok": True, **stat}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        return JSONResponse({"error": "question 不能为空"}, status_code=400)

    ensure_index()
    hits = store.index.search(question)

    async def gen():
        # 1) 先把命中的资料推给前端（用于展示"参考来源"）
        yield sse({
            "type": "hits",
            "hits": [
                {"i": i, "source": h["source"], "head": h.get("head", ""), "score": h["score"],
                 "preview": h["text"].replace("\n", " ")[:110]}
                for i, h in enumerate(hits, start=1)
            ],
        })

        # 2) 没有命中 → 兜底
        if not hits:
            async for piece in _stream_text(prompt.NO_HIT_ANSWER):
                yield sse({"type": "delta", "text": piece})
            yield sse({"type": "done", "mode": "no_hit"})
            return

        # 3) 没有 key → 检索演示
        if not config.HAS_KEY:
            async for piece in _stream_text(_demo_answer(hits)):
                yield sse({"type": "delta", "text": piece})
            yield sse({"type": "done", "mode": "demo"})
            return

        # 4) 正常路径：检索结果 + 历史 → 大模型流式回答
        history = [t.model_dump() for t in req.history[-config.MAX_HISTORY:]]
        messages = prompt.build_messages(question, hits, history)
        try:
            async for piece in llm.stream_chat(messages):
                yield sse({"type": "delta", "text": piece})
            yield sse({"type": "done", "mode": "llm"})
        except Exception as exc:
            yield sse({"type": "error", "message": f"模型调用失败：{exc}"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
