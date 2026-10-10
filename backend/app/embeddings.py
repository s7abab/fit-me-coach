from functools import lru_cache
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"   # 384 numbers per text, handles longer chunks than MiniLM

@lru_cache
def get_model():
    # Loads the model once and reuses it
    return SentenceTransformer(MODEL_NAME)

def embed(texts):
    return get_model().encode(texts, normalize_embeddings=True, batch_size=32)