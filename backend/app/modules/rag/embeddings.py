"""
DevVision AI - Local Embedding Model Implementation.

Wraps BAAI/bge-small-en-v1.5 using sentence-transformers.
Executes 100% locally with zero external API calls.
"""

import asyncio
from typing import List
import structlog
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.modules.rag.protocols import EmbeddingModel

logger = structlog.get_logger(__name__)


class BgeEmbeddingModel(EmbeddingModel):
    """
    Local implementation of EmbeddingModel protocol using BAAI/bge-small-en-v1.5.
    Computes 384-dimensional dense vectors.
    """

    def __init__(
        self,
        model_name: str | None = None,
        model_version: str | None = None,
        dimension: int | None = None,
    ):
        settings = get_settings()
        self._model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._model_version = model_version or settings.EMBEDDING_MODEL_VERSION
        self._dimension = dimension or settings.EMBEDDING_DIMENSION
        self._model: SentenceTransformer | None = None

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("loading_embedding_model", model_name=self._model_name)
            # Load model locally; sentence-transformers caches in ~/.cache/huggingface
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings for a list of passages asynchronously in thread pool."""
        if not texts:
            return []

        def _encode() -> List[List[float]]:
            model = self._load_model()
            # normalize_embeddings=True for cosine similarity
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return embeddings.tolist()

        return await asyncio.to_thread(_encode)

    async def embed_query(self, query: str) -> List[float]:
        """Compute dense vector embedding for a search query."""
        results = await self.embed_texts([query])
        return results[0]
