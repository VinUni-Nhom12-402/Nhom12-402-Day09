# -*- coding: utf-8 -*-
"""
workers/retrieval.py — Retrieval Worker
Sprint 2: Retrieve chunks từ ChromaDB, trả về evidence cho pipeline.

Worker Contract (xem contracts/worker_contracts.yaml → retrieval_worker):
─────────────────────────────────────────────────────────────────────────
  Input  (từ AgentState):
      task            : str   — câu hỏi cần tìm evidence
      top_k           : int   — số chunks cần lấy (default 3)

  Output (vào AgentState):
      retrieved_chunks  : list[dict]  — [{text, source, score, metadata}]
      retrieved_sources : list[str]   — unique list of source filenames
      worker_io_logs    : list[dict]  — append 1 log entry
      history           : list[str]  — append 1 summary line

  Error format:
      worker_io_logs[-1]["error"] = {"code": "RETRIEVAL_FAILED", "reason": str}
      retrieved_chunks = [], retrieved_sources = []

Chạy test độc lập:
    python workers/retrieval.py
"""

import os
import sys
import warnings

# Dùng model đã cache, không cần kết nối HuggingFace khi chạy offline
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
from datetime import datetime
from typing import Any

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

WORKER_NAME    = "retrieval_worker"
CHROMA_PATH    = "./chroma_db"
COLLECTION_NAME = "day09_docs"
DEFAULT_TOP_K  = 3
EMBED_DIM      = 384          # all-MiniLM-L6-v2 dimension


# ─────────────────────────────────────────────
# 1. Embedding — 3 tiers với fallback tự động
# ─────────────────────────────────────────────

_cached_embed_fn = None

def _get_embedding_fn():
    """
    Trả về (embed_fn, backend_name). Lazy-load caching để không load lại weights nhiều lần.
    """
    global _cached_embed_fn
    if _cached_embed_fn is not None:
        return _cached_embed_fn

    # Option A: Sentence Transformers (offline, không cần API key)
    try:
        import os
        os.environ["TRANSFORMERS_VERBOSITY"] = "error"
        import logging
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)

        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        def embed(text: str) -> list:
            return model.encode([text])[0].tolist()
        _cached_embed_fn = (embed, "sentence-transformers/all-MiniLM-L6-v2")
        return _cached_embed_fn
    except ImportError:
        pass

    # Option B: OpenAI (cần API key)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        def embed(text: str) -> list:
            resp = client.embeddings.create(input=text, model="text-embedding-3-small")
            return resp.data[0].embedding
        return (embed, "openai/text-embedding-3-small")
    except ImportError:
        pass

    # Fallback: random embeddings cho test (KHÔNG dùng production)
    import random
    def embed(text: str) -> list:
        return [random.random() for _ in range(384)]
    print("WARNING: Using random embeddings (test only). Install sentence-transformers.")
    return (embed, "random-fallback")


# ─────────────────────────────────────────────
# 2. ChromaDB — kết nối & tự tạo collection
# ─────────────────────────────────────────────

def _get_chroma_collection():
    """
    Kết nối ChromaDB tại CHROMA_PATH.
    Tự tạo collection 'day09_docs' nếu chưa tồn tại.
    Trả về (collection, is_empty: bool).
    """
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    is_empty = collection.count() == 0
    if is_empty:
        warnings.warn(
            f"⚠️  [retrieval_worker] Collection '{COLLECTION_NAME}' trống!\n"
            "   Chạy index script trước để nạp dữ liệu vào ChromaDB.",
            stacklevel=3,
        )
    return collection, is_empty


# ─────────────────────────────────────────────
# 3. Dense Retrieval — core logic
# ─────────────────────────────────────────────

def retrieve_dense(
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> tuple[list[dict], dict]:
    """
    Embed query rồi query ChromaDB, trả về top_k chunks.

    Args:
        query : câu hỏi / search query
        top_k : số chunks cần lấy

    Returns:
        (chunks, meta) trong đó:
            chunks : list[{"text", "source", "score", "metadata"}]
            meta   : {"embed_backend": str, "collection_count": int,
                      "query_top_k": int, "returned": int}
    """
    # 3.1  Embed
    embed_fn, embed_backend = _get_embedding_fn()
    query_vector = embed_fn(query)

    # 3.2  Connect collection
    collection, _ = _get_chroma_collection()
    total_docs = collection.count()

    # Tránh lỗi nếu top_k lớn hơn số doc đang có
    effective_k = min(top_k, total_docs) if total_docs > 0 else 0

    if effective_k == 0:
        return [], {
            "embed_backend": embed_backend,
            "collection_count": total_docs,
            "query_top_k": top_k,
            "returned": 0,
        }

    # 3.3  Query
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=effective_k,
        include=["documents", "distances", "metadatas"],
    )

    # 3.4  Parse — score = 1 − cosine_distance  →  [0, 1]
    # Chỉ giữ chunks có score >= 0.01 (loại bỏ docs hoàn toàn không liên quan)
    SCORE_THRESHOLD = 0.04
    chunks: list[dict] = []
    docs      = results.get("documents", [[]])[0]
    distances = results.get("distances",  [[]])[0]
    metadatas = results.get("metadatas",  [[]])[0]

    for doc, dist, meta in zip(docs, distances, metadatas):
        score = round(float(1.0 - dist), 4)
        score = max(0.0, min(1.0, score))
        if score >= SCORE_THRESHOLD:
            chunks.append({
                "text"    : doc,
                "source"  : meta.get("source", "unknown"),
                "score"   : score,
                "metadata": meta,
            })

    return chunks, {
        "embed_backend"   : embed_backend,
        "collection_count": total_docs,
        "query_top_k"     : top_k,
        "returned"        : len(chunks),
    }


# ─────────────────────────────────────────────
# 4. Worker Entry Point — Worker Contract
# ─────────────────────────────────────────────

def run(state: dict) -> dict:
    """
    Entry point — gọi từ graph.py / retrieval_worker_node().

    Đọc state["task"] và state["retrieval_top_k"],
    ghi kết quả vào state theo Worker Contract.
    """
    task  = state.get("task", "").strip()
    top_k = int(state.get("top_k", DEFAULT_TOP_K))

    # Đảm bảo các list key tồn tại
    state.setdefault("workers_called", [])
    state.setdefault("history",        [])
    state.setdefault("worker_io_logs", [])

    state["workers_called"].append(WORKER_NAME)

    # Khởi tạo IO log entry (sẽ điền output/error sau)
    ts = datetime.now().isoformat(timespec="seconds")
    worker_io: dict = {
        "worker"    : WORKER_NAME,
        "timestamp" : ts,
        "input"     : {"task": task, "top_k": top_k},
        "output"    : None,
        "error"     : None,
    }

    try:
        # ── Validate input ──────────────────────────────────
        if not task:
            raise ValueError("state['task'] rỗng — không có câu hỏi để retrieve.")

        # ── Retrieve ────────────────────────────────────────
        chunks, retrieval_meta = retrieve_dense(task, top_k=top_k)

        # Unique sources, giữ thứ tự xuất hiện
        sources: list[str] = []
        seen: set           = set()
        for c in chunks:
            src = c["source"]
            if src not in seen:
                sources.append(src)
                seen.add(src)

        # ── Write state ──────────────────────────────────────
        state["retrieved_chunks"]  = chunks
        state["retrieved_sources"] = sources

        worker_io["output"] = {
            "chunks_count" : len(chunks),
            "sources"      : sources,
            "retrieval_meta": retrieval_meta,
        }

        state["history"].append(
            f"[{WORKER_NAME}] retrieved {len(chunks)} chunks "
            f"via {retrieval_meta['embed_backend']} | sources={sources}"
        )

    except Exception as exc:
        # ── Error path — theo contract ───────────────────────
        err_msg = str(exc)
        worker_io["error"] = {
            "code"  : "RETRIEVAL_FAILED",
            "reason": err_msg,
        }
        state["retrieved_chunks"]  = []
        state["retrieved_sources"] = []
        state["history"].append(
            f"[{WORKER_NAME}] ERROR — RETRIEVAL_FAILED: {err_msg}"
        )

    # Luôn ghi IO log dù thành công hay lỗi
    state["worker_io_logs"].append(worker_io)

    return state


# ─────────────────────────────────────────────
# 5. Standalone Test
# ─────────────────────────────────────────────


def _safe(text: str) -> str:
    """Encode-safe cho Windows console (cp1252/gbk). Thay ky tu la bang '?'."""
    enc = sys.stdout.encoding or "utf-8"
    return text.encode(enc, errors="replace").decode(enc)

if __name__ == "__main__":
    print("=" * 50)
    print("Retrieval Worker — Standalone Test")
    print("=" * 50)

    test_queries = [
        "SLA ticket P1 là bao lâu?",
        "Điều kiện được hoàn tiền là gì?",
        "Ai phê duyệt cấp quyền Level 3?",
    ]

    for query in test_queries:
        print(f"\n[Run] Query: {_safe(query)}")
        result = run({"task": query})
        chunks = result.get("retrieved_chunks", [])
        print(f"  Retrieved: {len(chunks)} chunks")
        for c in chunks[:2]:
            preview = _safe(c["text"][:80].replace("\n", " "))
            print(f"    [{c['score']:.3f}] {c['source']}: {preview}...")
        print(f"  Sources: {result.get('retrieved_sources', [])}")

    print("\n[OK] retrieval_worker test done.")