"""Text embeddings (384-dim).

Uses sentence-transformers `all-MiniLM-L6-v2` when the optional `embeddings` extra is
installed and the model is available locally; otherwise a deterministic feature-hashing
embedder (word unigrams + bigrams + character trigrams, signed hashing, L2-normalised) so the
product works fully offline. See docs/adr/0003-offline-embeddings.md.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from functools import lru_cache
from typing import Protocol

import numpy as np

from twinpm.db.models import EMBED_DIM

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = (
    "a an and are as at be but by for from has have i in is it its of on or our so that the "
    "their this to was we were will with you your can not no do does just"
)
STOPWORDS = frozenset(_STOP.split())


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _bucket(token: str) -> tuple[int, float]:
    h = hashlib.blake2b(token.encode(), digest_size=8).digest()
    v = int.from_bytes(h, "little")
    return v % EMBED_DIM, 1.0 if (v >> 63) & 1 else -1.0


class HashingEmbedder:
    name = "hashing-384-v1"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), EMBED_DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            words = [w for w in _TOKEN.findall(text.lower()) if w not in STOPWORDS]
            feats: list[tuple[str, float]] = [(w, 1.0) for w in words]
            feats += [(f"{a}_{b}", 0.7) for a, b in itertools.pairwise(words)]
            for w in words:
                padded = f"#{w}#"
                feats += [(padded[i : i + 3], 0.25) for i in range(len(padded) - 2)]
            for tok, weight in feats:
                idx, sign = _bucket(tok)
                out[row, idx] += sign * weight
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


class SentenceTransformerEmbedder:
    name = "all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


@lru_cache
def get_embedder() -> Embedder:
    try:
        return SentenceTransformerEmbedder()
    except Exception:  # extra not installed or model not cached: stay offline
        return HashingEmbedder()


def download() -> None:
    """Fetch the transformer model into the local cache (build time, not request time)."""
    from sentence_transformers import SentenceTransformer

    SentenceTransformer("all-MiniLM-L6-v2")


def embed(texts: list[str]) -> np.ndarray:
    return get_embedder().embed(texts) if texts else np.zeros((0, EMBED_DIM), np.float32)


if __name__ == "__main__":
    download()
    print(get_embedder().name)
