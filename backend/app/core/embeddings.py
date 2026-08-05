import hashlib
import logging
from abc import ABC, abstractmethod

import numpy as np

from app.config import Settings

logger = logging.getLogger("linguaql.embeddings")


class Embedder(ABC):
    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class HashingEmbedder(Embedder):
    """Deterministic hashing-trick embedding. No dependencies, no network.

    Tokenises on non-alphanumerics, hashes each token into a fixed-width vector
    with a signed bucket, then L2-normalises. Good enough to cluster columns of
    the same table/topic for small schemas.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        tokens = "".join(c.lower() if c.isalnum() else " " for c in text).split()
        for tok in tokens:
            h = hashlib.md5(tok.encode()).digest()
            bucket = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[bucket] += sign
        norm = np.linalg.norm(v)
        if norm > 0:
            v /= norm
        return v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t).tolist() for t in texts]


class LocalEmbedder(Embedder):
    """sentence-transformers all-MiniLM-L6-v2 (384-dim). Optional dependency."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


class OpenAIEmbedder(Embedder):
    """OpenAI text-embedding-3-small (1536-dim). Requires OPENAI_API_KEY."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


def build_embedder(settings: Settings) -> Embedder:
    """Factory with graceful fallback to the always-available hashing embedder.

    A fallback is logged at WARNING so a misconfiguration (e.g. EMBEDDER=openai
    with the package missing or no key) is never silent.
    """
    choice = settings.embedder
    if choice == "openai":
        if not settings.openai_api_key:
            logger.warning(
                "EMBEDDER=openai but OPENAI_API_KEY is empty; "
                "falling back to HashingEmbedder."
            )
        else:
            try:
                return OpenAIEmbedder(settings.openai_api_key)
            except Exception as e:
                logger.warning(
                    "EMBEDDER=openai failed to initialise (%s); "
                    "falling back to HashingEmbedder. "
                    "Is the 'openai' package installed?",
                    e,
                )
    elif choice == "local":
        try:
            return LocalEmbedder()
        except Exception as e:
            logger.warning(
                "EMBEDDER=local failed to initialise (%s); "
                "falling back to HashingEmbedder. "
                "Is 'sentence-transformers' installed?",
                e,
            )
    return HashingEmbedder(dim=settings.embed_dim)
