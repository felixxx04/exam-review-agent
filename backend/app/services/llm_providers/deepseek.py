"""Provider adapter for DeepSeek's OpenAI-compatible chat completions API."""

from typing import Optional

import httpx

from app.services.llm_providers.base import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    """Provider adapter for DeepSeek's OpenAI-compatible chat completions API."""

    _chat_path: str = "/v1/chat/completions"
    _provider_name: str = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "deepseek-chat",
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        super().__init__(api_key=api_key, base_url=base_url, model=model, client=client)
