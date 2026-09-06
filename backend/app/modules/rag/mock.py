"""
DevVision AI - Mock implementations for RAG Protocols.

Used in fast deterministic unit tests and CI without requiring GPU, HuggingFace weights,
or running Ollama/llama.cpp daemons.
"""

from typing import List, Tuple
from app.modules.rag.protocols import EmbeddingModel, RerankerModel, LanguageModel


class MockEmbeddingModel(EmbeddingModel):
    """Deterministic mock embedding model."""

    def __init__(self, dimension: int = 384, model_name: str = "mock-bge-small-en-v1.5"):
        self._dim = dimension
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return "mock-v1"

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Generates deterministic non-zero normalized vector based on string hash
        results = []
        for text in texts:
            seed = sum(ord(c) for c in text) % 1000 + 1
            # Produce float vector of length self._dim
            vec = [float((seed + i) % 10) / 10.0 for i in range(self._dim)]
            # Normalize
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            results.append([round(x / norm, 6) for x in vec])
        return results

    async def embed_query(self, query: str) -> List[float]:
        res = await self.embed_texts([query])
        return res[0]


class MockRerankerModel(RerankerModel):
    """Deterministic mock reranker model."""

    def __init__(self, model_name: str = "mock-bge-reranker-base"):
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return "mock-v1"

    async def rerank(
        self, query: str, passages: List[str], top_k: int = 5
    ) -> List[Tuple[int, float]]:
        # Return descending scores based on original indices
        results = []
        for i, _ in enumerate(passages):
            # Deterministic score
            score = 1.0 / (i + 1.5)
            results.append((i, round(score, 4)))
        return results[:top_k]


class MockLanguageModel(LanguageModel):
    """Configurable mock language model for testing citation extraction and responses."""

    def __init__(
        self,
        default_response: str = "According to the architectural specification, the system supports real-time ingestion [1]. Furthermore, authentication is enforced on every endpoint [2].",
        model_name: str = "mock-qwen2.5-coder:7b",
    ):
        self._response = default_response
        self._model_name = model_name
        self.call_count = 0
        self.last_system_prompt: str | None = None
        self.last_user_prompt: str | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    def set_response(self, response: str) -> None:
        self._response = response

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        self.call_count += 1
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return self._response

    async def health(self) -> bool:
        return True
