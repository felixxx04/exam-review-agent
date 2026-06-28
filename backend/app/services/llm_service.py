"""LLM Service with circuit breaker, retry logic, and fallback chain."""

import asyncio
import logging
import random
import time
from typing import Optional, Union

from app.core.config import settings
from app.core.exceptions import LLMProviderError
from app.services.llm_providers.deepseek import DeepSeekProvider
from app.services.llm_providers.glm import GLMProvider
from app.services.llm_providers.minimax import MiniMaxProvider
from app.services.llm_providers.volcengine import VolcengineProvider

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Tracks consecutive failures and opens the circuit after a threshold.

    When open, requests are skipped until the recovery timeout elapses.
    A successful call while the circuit is closed resets the failure count.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0

    def is_open(self) -> bool:
        """Return True if the circuit is open (requests should be skipped)."""
        if self._failure_count >= self._failure_threshold:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed < self._recovery_timeout:
                return True
        return False

    def record_failure(self) -> None:
        """Record a failure and update the last-failure timestamp."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

    def record_success(self) -> None:
        """Record a success, resetting the failure count if circuit is closed."""
        if not self.is_open():
            self._failure_count = 0

    def reset(self) -> None:
        """Force-reset the circuit to closed state."""
        self._failure_count = 0
        self._last_failure_time = 0.0


class LLMService:
    """Multi-model LLM service with circuit breakers, retries, and fallback.

    Features:
    - Unified ``invoke()`` accepting messages or a plain string prompt.
    - Per-provider circuit breaker to skip failing providers.
    - Retry with exponential backoff and jitter (up to 3 attempts).
    - Configurable fallback chain (e.g. DeepSeek -> GLM -> MiniMax).
    - Latency and token-usage logging.
    """

    def __init__(
        self,
        providers: dict,
        default_provider: str = "deepseek",
        fallback_chain: Optional[list[str]] = None,
        max_retries: int = 3,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._providers = providers
        self._default_provider = default_provider
        self._fallback_chain: list[str] = fallback_chain if fallback_chain is not None else ["glm", "minimax"]
        self._max_retries = max_retries
        self._breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(failure_threshold, recovery_timeout)
            for name in providers
        }

    async def invoke(
        self,
        messages: Union[list[dict], str],
        **kwargs,
    ) -> str:
        """Invoke the LLM with automatic fallback and retry.

        Args:
            messages: A list of chat message dicts or a plain string prompt.
            **kwargs: Additional parameters forwarded to the provider
                      (e.g. temperature, max_tokens).

        Returns:
            The response text from the LLM.

        Raises:
            LLMProviderError: When all providers (including fallbacks) fail.
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        provider_names = self._build_provider_chain()
        last_error: Optional[Exception] = None

        for provider_name in provider_names:
            breaker = self._breakers.get(provider_name)
            if breaker is not None and breaker.is_open():
                logger.warning(
                    "Circuit breaker open for %s, skipping", provider_name
                )
                continue

            provider = self._providers.get(provider_name)
            if provider is None:
                logger.warning("Unknown provider %s, skipping", provider_name)
                continue

            result, error = await self._invoke_with_retries(
                provider, provider_name, messages, breaker, **kwargs
            )
            if error is None:
                return result  # type: ignore[return-value]
            last_error = error

        raise LLMProviderError(
            "all",
            f"All LLM providers failed. Last error: {last_error}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_provider_chain(self) -> list[str]:
        """Build the ordered list of providers to try."""
        chain = [self._default_provider]
        for name in self._fallback_chain:
            if name not in chain:
                chain.append(name)
        return chain

    async def _invoke_with_retries(
        self,
        provider,
        provider_name: str,
        messages: list[dict],
        breaker: Optional[CircuitBreaker],
        **kwargs,
    ) -> tuple[Optional[str], Optional[Exception]]:
        for attempt in range(1, self._max_retries + 1):
            t0 = time.monotonic()
            try:
                result = await provider.invoke(messages, **kwargs)
                elapsed = time.monotonic() - t0
                logger.info(
                    "%s succeeded in %.2fs (attempt %d)",
                    provider_name,
                    elapsed,
                    attempt,
                )
                if breaker is not None:
                    breaker.record_success()
                return result, None
            except LLMProviderError as exc:
                elapsed = time.monotonic() - t0
                logger.warning(
                    "%s attempt %d failed after %.2fs: %s",
                    provider_name,
                    attempt,
                    elapsed,
                    exc,
                )
                if breaker is not None:
                    breaker.record_failure()
                if attempt >= self._max_retries:
                    return None, exc
                wait = (2 ** (attempt - 1)) + random.uniform(0, 1)
                await asyncio.sleep(wait)

        return None, None  # Unreachable, but satisfies type checker


def get_default_llm_service() -> LLMService:
    """Factory that builds an LLMService from application settings.

    This is the recommended way to obtain a pre-configured instance.
    A shared ``httpx.AsyncClient`` is used across all providers for
    connection pooling.
    """
    import httpx

    shared_client = httpx.AsyncClient(timeout=60.0)

    providers = {
        "deepseek": DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            client=shared_client,
        ),
        "glm": GLMProvider(
            api_key=settings.glm_api_key,
            base_url=settings.glm_base_url,
            client=shared_client,
        ),
        "minimax": MiniMaxProvider(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            client=shared_client,
        ),
        "volcengine": VolcengineProvider(
            api_key=settings.volcengine_api_key,
            base_url=settings.volcengine_base_url,
            client=shared_client,
        ),
    }
    return LLMService(
        providers=providers,
        default_provider=settings.default_llm_provider,
    )
