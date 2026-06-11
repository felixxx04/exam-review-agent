"""Provider adapter for MiniMax's OpenAI-compatible chat completions API."""

from typing import Optional

import httpx

from app.services.llm_providers.base import OpenAICompatibleProvider


class MiniMaxProvider(OpenAICompatibleProvider):
    """Provider adapter for MiniMax's OpenAI-compatible chat completions API."""

    _chat_path: str = "/v1/chat/completions"
    _provider_name: str = "minimax"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "abab6.5s-chat",
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, model=model, client=client)
