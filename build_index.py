# -*- coding: utf-8 -*-
"""
build_index.py — Build ChromaDB index từ data/docs/
────────────────────────────────────────────────────
Đọc tất cả .txt trong data/docs/, chunk theo paragraph,
embed bằng all-MiniLM-L6-v2, nạp vào ChromaDB collection day09_docs.

Chạy:
    python build_index.py

Sau khi chạy xong → thư mục ./chroma_db/ sẽ có dữ liệu,
và workers/retrieval.py có thể query bình thường.
"""

import os
import re
import sys
import hashlib
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

DOCS_DIR        = Path("./data/docs")
CHROMA_PATH     = "./chroma_db"
COLLECTION_NAME = "day09_docs"
CHUNK_MIN_CHARS = 60    # bỏ đoạn quá ngắn (header, dòng trống)
CHUNK_MAX_CHARS = 800   # cắt đoạn quá dài


# ─────────────────────────────────────────────
# 1. Parse file header (5 dòng đầu)
# ─────────────────────────────────────────────

def parse_header(lines: list[str]) -> dict:
    """
    Trích metadata từ các dòng đầu file theo format:
        Key: Value
    Ví dụ: Source: policy/refund-v4.pdf
    """
    meta = {}
    for line in lines[:10]:
        line = line.strip()
        if ":" in line and not line.startswith("==="):
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()
    return meta


# ─────────────────────────────────────────────
# 2. Chunking — theo paragraph/section
# ─────────────────────────────────────────────

def split_into_chunks(text: str, filename: str) -> list[dict]:
    """
    Tách văn bản thành chunks:
    - Ưu tiên tách theo section (===...===)
    - Nếu section quá dài → tách tiếp theo paragraph (dòng trống)
    - Lọc bỏ chunk < CHUNK_MIN_CHARS ký tự

    Trả về list[{"chunk_text": str, "section": str}]
    """
    chunks_out = []
    current_section = "intro"

    # Tách theo section header  ===Tên section===
    section_pattern = re.compile(r"^===\s*(.+?)\s*===\s*$", re.MULTILINE)
    parts = section_pattern.split(text)

    # parts = [trước section 1, heading1, body1, heading2, body2, ...]
    i = 0
    while i < len(parts):
        segment = parts[i].strip()

        # Nếu là heading — lưu lại làm label
        if i % 2 == 1:
            current_section = segment
            i += 1
            continue

        # Tách nội dung theo đoạn (2 newline = paragraph break)
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", segment) if p.strip()]

        for para in paragraphs:
            if len(para) < CHUNK_MIN_CHARS:
                continue
            # Nếu đoạn quá dài → cắt thô theo ký tự
            if len(para) > CHUNK_MAX_CHARS:
                for j in range(0, len(para), CHUNK_MAX_CHARS):
                    sub = para[j : j + CHUNK_MAX_CHARS].strip()
                    if len(sub) >= CHUNK_MIN_CHARS:
                        chunks_out.append({
                            "chunk_text": sub,
                            "section"   : current_section,
                        })
            else:
                chunks_out.append({
                    "chunk_text": para,
                    "section"   : current_section,
                })
        i += 1

    return chunks_out


# ─────────────────────────────────────────────
# 3. Load & process tất cả file .txt
# ─────────────────────────────────────────────

def load_all_docs(docs_dir: Path) -> list[dict]:
    """
    Đọc từng .txt, parse header, chunk nội dung.
    Trả về list[{id, text, source, section, metadata}]
    """
    all_records = []

    txt_files = sorted(docs_dir.glob("*.txt"))
    if not txt_files:
        print(f"❌ Không tìm thấy file .txt nào trong {docs_dir}")
        sys.exit(1)

    for filepath in txt_files:
        raw = filepath.read_text(encoding="utf-8")
        lines = raw.splitlines()

        # Parse header metadata
        file_meta = parse_header(lines)
        file_meta.setdefault("source", filepath.name)
        file_meta.setdefault("department", "unknown")
        file_meta.setdefault("effective date", "unknown")

        # Chunk
        chunks = split_into_chunks(raw, filepath.name)
        print(f"  [doc] {filepath.name:35s} -> {len(chunks):3d} chunks")

        for idx, chunk in enumerate(chunks):
            # Deterministic ID: hash(filename + idx)
            uid = hashlib.md5(
                f"{filepath.name}::{idx}".encode()
            ).hexdigest()[:12]

            all_records.append({
                "id"      : uid,
                "text"    : chunk["chunk_text"],
                "source"  : filepath.name,
                "section" : chunk["section"],
                "metadata": {
                    "source"    : filepath.name,
                    "section"   : chunk["section"],
                    "department": file_meta.get("department", "unknown"),
                    "effective_date": file_meta.get("effective date", "unknown"),
                    "doc_source": file_meta.get("source", filepath.name),
                    "chunk_idx" : idx,
                },
            })

    return all_records


# ─────────────────────────────────────────────
# 4. Embed — dùng all-MiniLM-L6-v2
# ─────────────────────────────────────────────

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Batch embed với SentenceTransformers.
    Fallback sang OpenAI nếu không cài được.
    """
    try:
        import os
        os.environ["TRANSFORMERS_VERBOSITY"] = "error"
        import logging
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        
        from sentence_transformers import SentenceTransformer
        print("\n[embed] Backend: sentence-transformers/all-MiniLM-L6-v2")
        model = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = model.encode(texts, show_progress_bar=True, batch_size=32)
        return [v.tolist() for v in vecs]

    except ImportError:
        pass

    # Fallback: OpenAI
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        print("\n[embed] Backend: openai/text-embedding-3-small")
        client = OpenAI(api_key=api_key)
        embeddings = []
        batch = 50
        for i in range(0, len(texts), batch):
            resp = client.embeddings.create(
                input=texts[i : i + batch],
                model="text-embedding-3-small",
            )
            embeddings.extend([d.embedding for d in resp.data])
        return embeddings

    except Exception as e:
        print(f"[ERROR] Khong the embed: {e}")
        print("   Hay chay: pip install sentence-transformers")
        sys.exit(1)


# ─────────────────────────────────────────────
# 5. Nạp vào ChromaDB
# ─────────────────────────────────────────────

def build_chroma_index(records: list[dict], embeddings: list[list[float]]) -> None:
    """
    Upsert toàn bộ records + embeddings vào ChromaDB.
    Nếu collection đã tồn tại → xoá và tạo lại (rebuild sạch).
    """
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Xoá collection cũ nếu tồn tại (để rebuild sạch)
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"\n[del] Da xoa collection cu '{COLLECTION_NAME}'")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"[OK] Tao moi collection '{COLLECTION_NAME}' (cosine space)")

    # Upsert theo batch 100
    batch_size = 100
    total = len(records)
    for i in range(0, total, batch_size):
        batch_records = records[i : i + batch_size]
        batch_embeds  = embeddings[i : i + batch_size]

        collection.add(
            ids        = [r["id"]       for r in batch_records],
            documents  = [r["text"]     for r in batch_records],
            embeddings = batch_embeds,
            metadatas  = [r["metadata"] for r in batch_records],
        )
        print(f"   Upserted {min(i + batch_size, total):4d} / {total} chunks...")

    print(f"\n[OK] Index hoan tat -- {collection.count()} chunks trong ChromaDB")


# ─────────────────────────────────────────────
# 6. Verify — thử query nhanh
# ─────────────────────────────────────────────

def verify_index() -> None:
    """Query thử 1 câu để xác nhận index hoạt động."""
    import chromadb
    from sentence_transformers import SentenceTransformer

    print("\n[verify] Thu query: 'SLA P1 bao lau'")

    model = SentenceTransformer("all-MiniLM-L6-v2")
    vec   = model.encode(["SLA P1 bao lâu"])[0].tolist()

    client     = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(COLLECTION_NAME)

    results = collection.query(
        query_embeddings=[vec],
        n_results=3,
        include=["documents", "distances", "metadatas"],
    )

    docs      = results["documents"][0]
    distances = results["distances"][0]
    metas     = results["metadatas"][0]

    for doc, dist, meta in zip(docs, distances, metas):
        score = round(1 - dist, 4)
        print(f"  score={score:.4f}  src={meta['source']} / {meta['section']}")
        print(f"          {doc[:100].strip()}...")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    start = datetime.now()
    print("=" * 60)
    print("Build ChromaDB Index -- Day09 Lab")
    print(f"Docs dir   : {DOCS_DIR.resolve()}")
    print(f"Chroma path: {Path(CHROMA_PATH).resolve()}")
    print(f"Collection : {COLLECTION_NAME}")
    print("=" * 60)

    # Step 1 -- Load & chunk
    print("\n[step 1] Doc va chunk tai lieu...")
    records = load_all_docs(DOCS_DIR)
    total_chunks = len(records)
    print(f"\n   Tong: {total_chunks} chunks tu {len(list(DOCS_DIR.glob('*.txt')))} file")

    # Step 2 -- Embed
    texts = [r["text"] for r in records]
    embeddings = get_embeddings(texts)

    # Step 3 -- Index
    print("\n[step 3] Nap vao ChromaDB...")
    build_chroma_index(records, embeddings)

    # Step 4 — Verify
    try:
        verify_index()
    except Exception as e:
        print(f"[warn] Verify failed (khong anh huong index): {e}")

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n[done] Hoan thanh trong {elapsed:.1f}s")
    print("=" * 60)
    print("[next] Buoc tiep theo: python workers/retrieval.py")
