# -*- coding: utf-8 -*-
"""所有可调参数都集中在这里。改配置只改本文件 + .env，不用动业务代码。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ================= 1. 大模型（DeepSeek，OpenAI 兼容接口）=================
# 去 https://platform.deepseek.com/api_keys 申请，填进 .env
API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "900"))

# ================= 2. 知识库与切分 =================
DATA_DIR = BASE_DIR / "data"           # 你的 .md / .txt 资料放这里
STORAGE_DIR = BASE_DIR / "storage"     # 索引落盘目录（可删，删了重建）
CHROMA_DIR = STORAGE_DIR / "chroma"
CHUNK_FILE = STORAGE_DIR / "chunks.json"
COLLECTION = os.getenv("COLLECTION", "campus_docs")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "400"))      # 每段字数
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))  # 段间重叠字数

# ================= 3. 检索 =================
TOP_K = int(os.getenv("TOP_K", "5"))          # 最终喂给模型的片段数
RECALL_N = int(os.getenv("RECALL_N", "15"))   # 向量 / 关键词各自召回条数
VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.45"))  # 向量路在融合中的权重（中文小模型偏弱）
RRF_K = 60                                    # 融合排序常数，一般不用改
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.0"))  # 低于该融合分直接丢弃

# 向量化方式：default=Chroma 自带(英文小模型，零依赖，先跑通)
#            st=本地中文模型(需 pip install sentence-transformers，中文效果最好)
#            openai=任意 OpenAI 兼容的 embedding 接口(需 API_BASE/API_KEY)
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "default")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
EMBED_API_BASE = os.getenv("EMBED_API_BASE", "")
EMBED_API_KEY = os.getenv("EMBED_API_KEY", "")

# ================= 4. 服务 =================
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "6"))  # 带几轮历史进 Prompt

HAS_KEY = bool(API_KEY)
