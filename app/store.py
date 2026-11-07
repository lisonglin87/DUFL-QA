# -*- coding: utf-8 -*-
"""知识库：解析 → 按小节切分（带标题）→ 双路索引 → 混合检索 → 增量更新。

为什么这么设计（面试可以直接讲）：
1. **片段带标题**：每个片段记住「哪份文件 · 哪一节」，否则问"最近有什么大事"
   召不回只写了日期的那一段。
2. **双路召回**：向量擅长语义相近、BM25 擅长关键词精确命中；两路各取 15 条，
   用 1/rank 加权融合（向量权重 0.45，因为 Chroma 自带的是英文小模型）。
3. **增量更新**：用 manifest 记录每个文件的 mtime/size 和它产生的片段 id。
   只对新增/改动/删除的文件做向量化，未改动的一个字都不碰。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import jieba

from . import config

SUFFIXES = {".md", ".txt"}
MANIFEST = config.STORAGE_DIR / "manifest.json"


# ----------------------------------------------------------------------------
# 1. 读文件、切片段
# ----------------------------------------------------------------------------
def scan_files() -> dict[str, tuple[float, int]]:
    """返回 {相对路径: (mtime, size)}，用于判断哪些文件变了。"""
    out = {}
    for path in sorted(config.DATA_DIR.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            st = path.stat()
            out[path.relative_to(config.DATA_DIR).as_posix()] = (st.st_mtime, st.st_size)
    return out


def read_doc(rel: str) -> dict:
    path = config.DATA_DIR / rel
    return {
        "rel": rel,
        "source": path.name,
        "title": re.sub(r"^\d+[-_]\s*", "", path.stem),
        "text": path.read_text(encoding="utf-8", errors="ignore").strip(),
    }


def parse_sections(text: str) -> list[tuple[str, str]]:
    """按 #/##/### 拆小节，返回 [(标题路径, 正文)]。"""
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            sections.append((" / ".join(stack), body))
        buf.clear()

    for raw in text.split("\n"):
        m = re.match(r"^(#{1,4})\s*(.+)$", raw.rstrip())
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            stack = stack[: level - 1] + [title]
            continue
        buf.append(raw)
    flush()
    return sections


def split_body(body: str, size: int, overlap: int) -> list[str]:
    if len(body) <= size:
        return [body]
    pieces, buf = [], ""
    for para in [p for p in re.split(r"\n\s*\n", body) if p.strip()]:
        if len(para) > size:
            if buf:
                pieces.append(buf)
                buf = ""
            step = max(size - overlap, 50)
            pieces += [para[i:i + size] for i in range(0, len(para), step)]
            continue
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            pieces.append(buf)
            buf = (buf[-overlap:] + "\n" + para).strip() if overlap else para
    if buf:
        pieces.append(buf)
    return pieces


def build_chunks(doc: dict) -> list[dict]:
    """一份文件 → 若干片段（id 稳定，便于增量删除）。"""
    size, overlap = config.CHUNK_SIZE, config.CHUNK_OVERLAP
    sections = parse_sections(doc["text"]) or [(doc["title"], doc["text"])]
    chunks = []
    for i, (head, body) in enumerate(sections):
        for j, piece in enumerate(split_body(body, size, overlap)):
            chunks.append({
                "id": f"{doc['rel']}::{i}-{j}",
                "file": doc["rel"],
                "source": doc["source"],
                "title": doc["title"],
                "head": head,
                "text": piece.strip(),
            })
    return chunks


def index_text(c: dict) -> str:
    """进索引的文本 = 文件名 + 小节标题 + 正文。"""
    return f"{c['title']} {c['head']}\n{c['text']}"


# ----------------------------------------------------------------------------
# 2. BM25
# ----------------------------------------------------------------------------
STOPWORDS = {"的", "了", "是", "在", "和", "与", "及", "或", "有", "对", "个", "我", "你",
             "他", "她", "它", "这", "那", "什么", "怎么", "如何", "请问", "一下", "可以",
             "吗", "呢", "吧", "啊", "要", "会", "能", "想", "去", "来", "上", "下", "里"}
TOKEN_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    """分词 + 中文二元组。

    只靠 jieba 会踩粒度不一致的坑：查询里是"学院"，文档里是"日本语学院"，
    分词后就变成两个不同的词，召不回来。补一层二元组（学/院/学院…）能兜住。
    """
    out = []
    for w in jieba.lcut_for_search(text.lower()):
        w = w.strip()
        if len(w) < 2 or w in STOPWORDS or not TOKEN_RE.match(w):
            continue
        out.append(w)
    for run in re.findall(r"[\u4e00-\u9fa5]{2,}", text):
        out += [run[i:i + 2] for i in range(len(run) - 1)]
    return out


# 学生口语和官方文件用词常常对不上（"学院" vs "院系"、"保研" vs "推免"）。
# 只在查询侧做一点点同义扩展，索引不动。
SYNONYMS = {
    "学院": ["院系"], "院系": ["学院"],
    "保研": ["推免"], "推免": ["保研"],
    "老师": ["教师"], "教师": ["老师"],
    "宿舍": ["住宿"], "食堂": ["餐饮"],
    "交换": ["交流"], "交流": ["交换"],
    "考试": ["考核"], "考核": ["考试"],
    "成绩": ["绩点"], "绩点": ["成绩"],
}


def expand_query(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        out += SYNONYMS.get(t, [])
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        self.df: Counter = Counter()
        for d in docs:
            self.df.update(set(d))
        self.idf = {w: math.log((self.n - f + 0.5) / (f + 0.5) + 1) for w, f in self.df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for d in self.docs:
            tf, dl = Counter(d), (len(d) or 1)
            s = 0.0
            for w in query:
                f = tf.get(w, 0)
                if not f:
                    continue
                s += self.idf.get(w, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


# ----------------------------------------------------------------------------
# 3. 索引（含增量）
# ----------------------------------------------------------------------------
def _embedding_function():
    from chromadb.utils import embedding_functions

    if config.EMBED_PROVIDER == "st":
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=config.EMBED_MODEL)
    if config.EMBED_PROVIDER == "openai":
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=config.EMBED_API_KEY or config.API_KEY,
            api_base=config.EMBED_API_BASE or config.BASE_URL,
            model_name=config.EMBED_MODEL)
    return embedding_functions.DefaultEmbeddingFunction()


class Index:
    def __init__(self):
        self.chunks: list[dict] = []
        self.bm25: BM25 | None = None
        self.col = None
        self.vector_ok = False
        self.manifest: dict[str, dict] = {}

    # ---------- 基础 ----------
    def _chroma(self, create: bool = False):
        import chromadb

        client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=chromadb.Settings(anonymized_telemetry=False))
        if create:
            try:
                client.delete_collection(config.COLLECTION)
            except Exception:
                pass
            return client.create_collection(name=config.COLLECTION,
                                            embedding_function=_embedding_function())
        return client.get_collection(name=config.COLLECTION,
                                     embedding_function=_embedding_function())

    def _add(self, chunks: list[dict]) -> None:
        for i in range(0, len(chunks), 200):
            part = chunks[i:i + 200]
            self.col.add(ids=[c["id"] for c in part],
                         documents=[index_text(c) for c in part],
                         metadatas=[{"source": c["source"], "head": c["head"]} for c in part])

    def _refresh_bm25(self) -> None:
        self.bm25 = BM25([tokenize(index_text(c)) for c in self.chunks])

    def _persist(self) -> None:
        config.CHUNK_FILE.write_text(json.dumps(self.chunks, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
        MANIFEST.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1),
                            encoding="utf-8")

    # ---------- 全量 ----------
    def rebuild(self) -> dict:
        config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        files = scan_files()
        if not files:
            raise RuntimeError(f"{config.DATA_DIR} 下没有找到 .md / .txt 文档")

        self.chunks, self.manifest = [], {}
        for rel in files:
            doc = read_doc(rel)
            chunks = build_chunks(doc)
            self.chunks += chunks
            self.manifest[rel] = {"key": list(files[rel]), "ids": [c["id"] for c in chunks]}

        try:
            self.col = self._chroma(create=True)
            self._add(self.chunks)
            self.vector_ok = True
        except Exception as exc:
            print(f"[warn] 向量索引不可用，降级为纯 BM25：{exc}")
            self.col, self.vector_ok = None, False

        self._refresh_bm25()
        self._persist()
        return {"mode": "full", "documents": len(files), "chunks": len(self.chunks),
                "vector": self.vector_ok, "added": len(files), "updated": 0,
                "removed": 0, "unchanged": 0}

    # ---------- 增量 ----------
    def update(self) -> dict:
        """只处理新增 / 修改 / 删除的文件，其余片段原样保留。"""
        if not self.chunks or not self.manifest:
            self.load()
        if not self.chunks:
            return self.rebuild()

        config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        files = scan_files()
        old = dict(self.manifest)
        added = updated = removed = unchanged = 0
        new_chunks: list[dict] = []
        keep: list[dict] = []
        delete_ids: list[str] = []

        for rel, meta in files.items():
            entry = old.get(rel)
            if entry and list(meta) == entry.get("key"):
                unchanged += 1
                continue
            if entry:
                updated += 1
                delete_ids += entry.get("ids", [])
            else:
                added += 1
            doc = read_doc(rel)
            chunks = build_chunks(doc)
            new_chunks += chunks
            old[rel] = {"key": list(meta), "ids": [c["id"] for c in chunks]}

        for rel, entry in list(old.items()):
            if rel not in files:
                removed += 1
                delete_ids += entry.get("ids", [])
                del old[rel]

        keep = [c for c in self.chunks if c["file"] in files and c["file"] not in
                {n["file"] for n in new_chunks}]
        self.chunks = keep + new_chunks
        self.manifest = old

        try:
            self.col = self._chroma() if self.col is None else self.col
            if delete_ids:
                try:
                    self.col.delete(ids=delete_ids)
                except Exception as exc:
                    print(f"[warn] 删除旧片段失败（首次建库时正常）：{exc}")
            if new_chunks:
                self._add(new_chunks)
            self.vector_ok = True
        except Exception as exc:
            print(f"[warn] 增量向量化失败，降级为纯 BM25：{exc}")
            self.col, self.vector_ok = None, False

        self._refresh_bm25()
        self._persist()
        return {"mode": "incremental", "documents": len(files), "chunks": len(self.chunks),
                "vector": self.vector_ok, "added": added, "updated": updated,
                "removed": removed, "unchanged": unchanged}

    # ---------- 加载 ----------
    def load(self) -> bool:
        if not config.CHUNK_FILE.exists():
            return False
        try:
            self.chunks = json.loads(config.CHUNK_FILE.read_text(encoding="utf-8"))
            self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
        except Exception:
            return False
        if not self.chunks:
            return False
        self._refresh_bm25()
        try:
            self.col = self._chroma()
            self.vector_ok = self.col.count() > 0
        except Exception as exc:
            print(f"[warn] 向量索引未加载，使用 BM25：{exc}")
            self.col, self.vector_ok = None, False
        return True

    # ---------- 检索 ----------
    def search(self, question: str, top_k: int | None = None) -> list[dict]:
        top_k = top_k or config.TOP_K
        if self.bm25 is None:
            return []
        by_id = {c["id"]: c for c in self.chunks}
        fused: dict[str, float] = {}

        q_tokens = expand_query(tokenize(question))
        kw = self.bm25.scores(q_tokens) if q_tokens else []
        for rank, i in enumerate(sorted(range(len(kw)), key=lambda i: -kw[i])[: config.RECALL_N], start=1):
            if kw[i] <= 0:
                continue
            fid = self.chunks[i]["id"]
            fused[fid] = fused.get(fid, 0.0) + 1.0 / rank

        if self.vector_ok and self.col is not None:
            try:
                res = self.col.query(query_texts=[question], n_results=config.RECALL_N)
                for rank, cid in enumerate(res.get("ids", [[]])[0], start=1):
                    fused[cid] = fused.get(cid, 0.0) + config.VECTOR_WEIGHT / rank
            except Exception as exc:
                print(f"[warn] 向量检索失败：{exc}")

        # 新闻稿词频噪声大（同一句"孔子学院"能出现几十次），检索时降权；
        # 制度/办事类文档才是用户真正要找的。
        def weight(fname: str) -> float:
            return 0.5 if fname.startswith("10-") else 1.0

        ranked = sorted(((cid, sc * weight(by_id[cid]["file"])) for cid, sc in fused.items()),
                        key=lambda kv: -kv[1])[:top_k]
        out = []
        for cid, score in ranked:
            c = by_id.get(cid)
            if c and score >= config.MIN_SCORE:
                out.append({"id": cid, "source": c["source"], "head": c["head"],
                            "text": c["text"], "score": round(score, 4)})

        # 同文档扩展：一篇文档常常分了好几节，只命中第一节会漏掉"常见问题"那节。
        # 给排名最前的两个文件各补一节（同文件里 BM25 得分最高的未选片段）。
        kw_by_id = {self.chunks[i]["id"]: kw[i] for i in range(len(self.chunks))}
        chosen = {h["id"] for h in out}
        tops = []
        for h in out[:1]:
            f = by_id[h["id"]]["file"]
            if f not in tops:
                tops.append(f)
        for f in tops:
            cands = [c for c in self.chunks if c["file"] == f and c["id"] not in chosen]
            if not cands:
                continue
            best = max(cands, key=lambda c: kw_by_id.get(c["id"], 0.0))
            out.append({"id": best["id"], "source": best["source"], "head": best["head"],
                        "text": best["text"], "score": round(kw_by_id.get(best["id"], 0.0) / 1000, 4)})
            chosen.add(best["id"])
        return out


index = Index()
