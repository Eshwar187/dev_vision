"""
DevVision AI - Self-Hosted Local LLM Client Implementations.

Supports local daemons (Ollama and llama.cpp server) via httpx.AsyncClient.
Zero calls to external proprietary APIs. 100% local, configurable timeouts, retries,
and strict fallback/error handling.
"""

import asyncio
from typing import Optional
import httpx
import structlog

from app.core.config import get_settings
from app.modules.rag.protocols import LanguageModel

logger = structlog.get_logger(__name__)


class OllamaLanguageModel(LanguageModel):
    """
    Local LanguageModel implementation communicating with a local Ollama daemon.
    Default endpoint: http://localhost:11434/api/chat
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self._model_name = model_name or settings.LLM_MODEL
        self._timeout = timeout_seconds or settings.LLM_REQUEST_TIMEOUT_SECONDS
        self._max_retries = max_retries or settings.LLM_MAX_RETRIES

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }

        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("message", {}).get("content", "").strip()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_err = exc
                logger.warning(
                    "ollama_request_failed",
                    attempt=attempt,
                    url=url,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(1.0)

        raise RuntimeError(f"Failed to communicate with local Ollama daemon at {url}: {last_err}")

    async def health(self) -> bool:
        """Verify Ollama daemon reachability."""
        url = f"{self._base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False


class LlamaCppLanguageModel(LanguageModel):
    """
    Local LanguageModel implementation communicating with llama.cpp server.
    Standard endpoint: http://localhost:8080/v1/chat/completions (OpenAI-compatible local server)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        settings = get_settings()
        self._base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self._model_name = model_name or settings.LLM_MODEL
        self._timeout = timeout_seconds or settings.LLM_REQUEST_TIMEOUT_SECONDS
        self._max_retries = max_retries or settings.LLM_MAX_RETRIES

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_response(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> str:
        url = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        last_err: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        return choices[0].get("message", {}).get("content", "").strip()
                    return ""
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_err = exc
                logger.warning(
                    "llamacpp_request_failed",
                    attempt=attempt,
                    url=url,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(1.0)

        raise RuntimeError(f"Failed to communicate with llama.cpp server at {url}: {last_err}")

    async def health(self) -> bool:
        """Verify llama.cpp server reachability."""
        url = f"{self._base_url}/health"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception:
            return False


def get_default_language_model() -> LanguageModel:
    """Factory creating configured local language model."""
    settings = get_settings()
    backend = settings.LLM_BACKEND.lower()
    if backend == "llamacpp_server":
        return LlamaCppLanguageModel()
    return OllamaLanguageModel()
