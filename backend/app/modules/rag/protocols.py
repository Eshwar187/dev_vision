"""
DevVision AI - RAG Model Decoupling Protocols.

Provides explicit Python Protocol interfaces for embedding, reranking,
and language generation. The platform business logic strictly depends
on these abstractions, ensuring 100% vendor independence and easy model swapping.
"""

from typing import List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class EmbeddingModel(Protocol):
    """Protocol for local vector embedding inference."""

    @property
    def model_name(self) -> str:
        """Name/path of the embedding model."""
        ...

    @property
    def model_version(self) -> str:
        """Version or commit hash of the model."""
        ...

    @property
    def dimension(self) -> int:
        """Output embedding dimension (e.g. 384 for bge-small-en-v1.5)."""
        ...

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Compute dense vector embeddings for a list of passages."""
        ...

    async def embed_query(self, query: str) -> List[float]:
        """Compute dense vector embedding for a search query."""
        ...


@runtime_checkable
class RerankerModel(Protocol):
    """Protocol for local cross-encoder passage reranking."""

    @property
    def model_name(self) -> str:
        """Name/path of the reranker model."""
        ...

    @property
    def model_version(self) -> str:
        """Version or commit hash of the model."""
        ...

    async def rerank(
        self, query: str, passages: List[str], top_k: int = 5
    ) -> List[Tuple[int, float]]:
        """
        Score and rank candidate passages against the query.
        Returns list of (passage_index, score) tuples sorted descending by score.
        """
        ...


@runtime_checkable
class LanguageModel(Protocol):
    """Protocol for self-hosted local language model generation."""

    @property
    def model_name(self) -> str:
        """Name/tag of the language model."""
        ...

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        """Generate text completion from system and user prompt strings."""
        ...

    async def health(self) -> bool:
        """Verify daemon/model connectivity and readiness."""
        ...
