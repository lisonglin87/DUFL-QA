# -*- coding: utf-8 -*-
"""大模型调用。DeepSeek 完全兼容 OpenAI 的接口，所以直接用 openai SDK。"""
from __future__ import annotations

from openai import AsyncOpenAI

from . import config

_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
    return _client


async def stream_chat(messages: list[dict]):
    """流式返回 token。没配 key 会抛 RuntimeError，由上层降级处理。"""
    if not config.API_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    resp = await client().chat.completions.create(
        model=config.MODEL,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
        stream=True,
    )
    async for chunk in resp:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        piece = getattr(delta, "content", None)
        if piece:
            yield piece
