from functools import lru_cache
from sentence_transformers import SentenceTransformer
from transformers.utils import logging as hf_logging

MODEL_NAME = "BAAI/bge-small-en-v1.5"   # 384 numbers per text, handles longer chunks than MiniLM

hf_logging.disable_progress_bar()   # no "Loading weights" bar on every run


def load_model(cls, name):
    # Use the copy on disk without calling the HF Hub; download only the first time
    try:
        return cls(name, local_files_only=True)
    except OSError:
        return cls(name)


@lru_cache
def get_model():
    # Loads the model once and reuses it
    return load_model(SentenceTransformer, MODEL_NAME)

def embed(texts):
    return get_model().encode(texts, normalize_embeddings=True, batch_size=32)
