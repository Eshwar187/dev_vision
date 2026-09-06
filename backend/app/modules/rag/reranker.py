"""
DevVision AI - Local Reranker Model Implementation.

Wraps BAAI/bge-reranker-base using sentence-transformers CrossEncoder.
Executes 100% locally with zero external API calls.
"""

import asyncio
from typing import List, Tuple
import structlog
from sentence_transformers import CrossEncoder

from app.core.config import get_settings
from app.modules.rag.protocols import RerankerModel

logger = structlog.get_logger(__name__)


class BgeRerankerModel(RerankerModel):
    """
    Local implementation of RerankerModel protocol using BAAI/bge-reranker-base.
    Calculates cross-encoder scores between a query and multiple candidate passages.
    """

    def __init__(
        self,
        model_name: str | None = None,
        model_version: str | None = None,
    ):
        settings = get_settings()
        self._model_name = model_name or settings.RERANKER_MODEL_NAME
        self._model_version = model_version or settings.RERANKER_MODEL_VERSION
        self._model: CrossEncoder | None = None

    def _load_model(self) -> CrossEncoder:
        if self._model is None:
            logger.info("loading_reranker_model", model_name=self._model_name)
            self._model = CrossEncoder(self._model_name)
        return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    async def rerank(
        self, query: str, passages: List[str], top_k: int = 5
    ) -> List[Tuple[int, float]]:
        """
        Score and rank candidate passages against the query.
        Returns list of (passage_index, score) tuples sorted descending by score.
        """
        if not passages:
            return []

        def _rerank_sync() -> List[Tuple[int, float]]:
            model = self._load_model()
            pairs = [[query, passage] for passage in passages]
            scores = model.predict(pairs, show_progress_bar=False)
            
            # Form indexed tuples: (original_index, score)
            indexed_scores = [(idx, float(score)) for idx, score in enumerate(scores)]
            
            # Sort descending by score, tie-break by original index ascending
            indexed_scores.sort(key=lambda x: (x[1], -x[0]), reverse=True)
            return indexed_scores[:top_k]

        return await asyncio.to_thread(_rerank_sync)
