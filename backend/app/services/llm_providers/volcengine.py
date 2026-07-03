"""Provider adapter for Volcengine Ark's OpenAI-compatible API."""

from app.services.llm_providers.base import OpenAICompatibleProvider


class VolcengineProvider(OpenAICompatibleProvider):
    _chat_path: str = "/chat/completions"
    _provider_name: str = "volcengine"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "deepseek-v3-2-251201",
        client=None,
    ) -> None:
        super().__init__(
            api_key=api_key, base_url=base_url, model=model, client=client
        )
