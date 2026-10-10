from functools import lru_cache
from sentence_transformers import CrossEncoder
from app.embeddings import embed

# Columns we want for every chunk: id, text, page, document title, document link
COLUMNS = "c.id, c.content, c.page, d.title, d.source_url"
FROM = "FROM chunks c JOIN documents d ON d.id = c.document_id"


@lru_cache
def get_reranker():
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def _vector_search(conn, q_vec, n):
    # Search by meaning
    return conn.execute(
        f"SELECT {COLUMNS} {FROM} ORDER BY c.embedding <=> %s LIMIT %s",
        (q_vec, n),
    ).fetchall()


def _keyword_search(conn, question, n):
    # Search by exact words (any word from the question)
    tsq = "to_tsquery('english', replace(plainto_tsquery('english', %s)::text, '&', '|'))"
    return conn.execute(
        f"SELECT {COLUMNS} {FROM} WHERE c.tsv @@ {tsq} ORDER BY ts_rank(c.tsv, {tsq}) DESC LIMIT %s",
        (question, question, n),
    ).fetchall()


def search(conn, question, k=5, candidates=20):
    q_vec = embed([question])[0]

    # Step 1: hybrid search, merging both lists with RRF
    scores, rows = {}, {}
    for results in (_vector_search(conn, q_vec, candidates), _keyword_search(conn, question, candidates)):
        for rank, row in enumerate(results):
            chunk_id = row[0]
            scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank)
            rows[chunk_id] = row

    shortlist = sorted(scores, key=scores.get, reverse=True)[:candidates]
    if not shortlist:
        return []

    # Step 2: rerank the shortlist and keep the best k
    rerank_scores = get_reranker().predict([(question, rows[i][1]) for i in shortlist])
    best = sorted(zip(shortlist, rerank_scores), key=lambda x: x[1], reverse=True)[:k]

    return [
        {"id": i, "content": rows[i][1], "page": rows[i][2], "title": rows[i][3], "url": rows[i][4], "score": float(s)}
        for i, s in best
    ]