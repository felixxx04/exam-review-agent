"""Base class for OpenAI-compatible LLM providers."""

import logging
from typing import Optional

import httpx

from app.core.exceptions import LLMProviderError
from app.services.ssl_certificates import ensure_valid_ssl_cert_file

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    """Base class for providers that implement an OpenAI-compatible chat
    completions API.

    Subclasses must set ``_chat_path`` and ``_provider_name`` and may
    override the default ``model`` value.
    """

    _chat_path: str = "/v1/chat/completions"
    _provider_name: str = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-3.5-turbo",
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = client

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}{self._chat_path}"

    async def invoke(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Send a chat completion request and return the response text."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        payload.update(kwargs)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is not None:
                response = await self._client.post(
                    self.chat_url, json=payload, headers=headers
                )
            else:
                ensure_valid_ssl_cert_file()
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        self.chat_url, json=payload, headers=headers
                    )
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                self._provider_name, f"HTTP request failed: {exc}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                self._provider_name, f"Unexpected error: {exc}"
            ) from exc

        if response.status_code != 200:
            raise LLMProviderError(
                self._provider_name,
                f"HTTP {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
        except Exception as exc:
            raise LLMProviderError(
                self._provider_name, f"Failed to parse response JSON: {exc}"
            ) from exc

        try:
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                self._provider_name, f"Unexpected response format: {exc}"
            ) from exc

        # Log token usage when present in the API response
        usage = data.get("usage", {})
        if usage:
            logger.info(
                "token usage for %s: prompt=%s, completion=%s, total=%s",
                self._provider_name,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
            )

        return content
