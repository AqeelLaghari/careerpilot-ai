"""Sentence embeddings (SBERT) + FAISS search. ATS Layer 3: matching by MEANING.

Model: sentence-transformers `all-MiniLM-L6-v2` (Reimers & Gurevych, Sentence-BERT).
Each text becomes a 384-number vector. Vectors are L2-normalised, so the inner
product of two vectors equals their cosine similarity. FAISS `IndexFlatIP` then
finds the most similar vectors exactly (no approximation).

The model (~90 MB) downloads once to the Hugging Face cache on first use.
"""
import logging
import os
from functools import lru_cache

import numpy as np

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384
log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    log.info("Loading embedding model %s (first time downloads ~90 MB)", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME, device="cpu")


def embed(texts: list[str]) -> np.ndarray:
    """Texts → float32 array (n, 384), each row length 1 (so dot product = cosine)."""
    if not texts:
        return np.zeros((0, DIM), dtype="float32")
    vecs = get_model().encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype="float32")


def build_index(vectors: np.ndarray):
    import faiss
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    return index


def search(index, query: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Top-k (row id, cosine similarity) for ONE query vector."""
    sims, ids = index.search(query.reshape(1, -1), min(k, index.ntotal))
    return [(int(i), float(s)) for i, s in zip(ids[0], sims[0]) if i >= 0]
