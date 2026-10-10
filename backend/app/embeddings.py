from pgvector import Vector

from app.config import settings
from app.voyage import post

DIMENSIONS = 1024   # must match the vector(...) size of chunks.embedding
BATCH_SIZE = 100    # texts per request, well under Voyage's per-request limits


def embed(texts, input_type="document"):
    # input_type is "document" for the chunks we store, "query" for a user's question
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        res = post("embeddings", {
            "model": settings.voyage_embed_model,
            "input": texts[start:start + BATCH_SIZE],
            "input_type": input_type,
            "output_dimension": DIMENSIONS,
        })
        vectors += [Vector(item["embedding"]) for item in sorted(res["data"], key=lambda d: d["index"])]
    return vectors
