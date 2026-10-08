import hashlib
import json
from pathlib import Path

import pymupdf4llm

from app.db import get_conn
from app.embeddings import embed

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk_words(text, size=250, overlap=50):
    words = text.split()
    pieces = []
    for start in range(0, len(words), size - overlap):
        piece = " ".join(words[start:start + size])
        if len(piece) > 100:
            pieces.append(piece)
    return pieces


def ingest_file(conn, path, meta):
    new_hash = file_hash(path)
    existing = conn.execute(
        "SELECT id, file_hash FROM documents WHERE filename = %s", (path.name,)
    ).fetchone()

    if existing and existing[1] == new_hash:
        print(f"Skip (unchanged): {path.name}")
        return

    # 1. Read PDF page by page as markdown (keeps tables)
    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True)
    rows = []
    for page_num, page in enumerate(pages, start=1):
        for piece in chunk_words(page["text"]):
            rows.append((page_num, piece))

    if not rows:
        print(f"WARNING: no text found in {path.name} (scanned PDF?)")
        return

    # 2. Embed all chunks
    vectors = embed([content for _, content in rows])

    # 3. Save everything in one transaction: all or nothing
    with conn.transaction():
        if existing:
            conn.execute("DELETE FROM documents WHERE id = %s", (existing[0],))
        doc_id = conn.execute(
            "INSERT INTO documents (title, filename, source_url, file_hash) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (meta.get("title", path.stem), path.name, meta.get("url"), new_hash),
        ).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (document_id, page, content, embedding) VALUES (%s, %s, %s, %s)",
                [(doc_id, page_num, content, vec) for (page_num, content), vec in zip(rows, vectors)],
            )

    action = "Re-ingested (changed)" if existing else "Ingested"
    print(f"{action}: {path.name} -> {len(pages)} pages, {len(rows)} chunks")


def main():
    sources_file = KNOWLEDGE_DIR / "sources.json"
    sources = json.loads(sources_file.read_text()) if sources_file.exists() else {}
    pdfs = sorted(KNOWLEDGE_DIR.glob("*.pdf"))

    with get_conn() as conn:
        for path in pdfs:
            ingest_file(conn, path, sources.get(path.name, {}))

        # Remove documents whose PDF was deleted from the folder
        on_disk = {p.name for p in pdfs}
        for doc_id, filename in conn.execute("SELECT id, filename FROM documents").fetchall():
            if filename not in on_disk:
                conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
                print(f"Removed (file deleted): {filename}")


if __name__ == "__main__":
    main()