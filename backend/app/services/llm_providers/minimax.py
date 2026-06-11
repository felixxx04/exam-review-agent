from typing import Optional

import httpx

from app.core.exceptions import LLMProviderError


class MiniMaxProvider:
    """Provider adapter for MiniMax's OpenAI-compatible chat completions API."""

    _chat_path: str = "/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "abab6.5s-chat",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

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
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.chat_url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                "MiniMax", f"HTTP request failed: {exc}"
            ) from exc
        except Exception as exc:
            raise LLMProviderError(
                "MiniMax", f"Unexpected error: {exc}"
            ) from exc

        if response.status_code != 200:
            raise LLMProviderError(
                "MiniMax",
                f"HTTP {response.status_code}: {response.text}",
            )

        try:
            data = response.json()
            content: str = data["choices"][0]["message"]["content"]
            return content
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "MiniMax", f"Unexpected response format: {exc}"
            ) from exc
