"""Tests for LLM Service with multi-model support, fallback chains, and circuit breaker."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import LLMProviderError
from app.services.llm_service import CircuitBreaker, LLMService


# ---------------------------------------------------------------------------
# CircuitBreaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        assert cb.is_open() is False

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is False
        cb.record_failure()
        assert cb.is_open() is True

    def test_reset_clears_failures(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True
        cb.reset()
        assert cb.is_open() is False

    def test_recovery_timeout_allows_retry(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True
        # Simulate the recovery timeout passing by manipulating _last_failure_time
        cb._last_failure_time = time.monotonic() - 31
        assert cb.is_open() is False

    def test_record_success_while_closed_resets(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.is_open() is False

    def test_record_success_while_open_does_not_close(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=30)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is True
        cb.record_success()
        # Should remain open until recovery timeout
        assert cb.is_open() is True


# ---------------------------------------------------------------------------
# LLMService tests
# ---------------------------------------------------------------------------


class TestLLMService:
    @pytest.fixture
    def mock_providers(self):
        return {
            "deepseek": AsyncMock(),
            "glm": AsyncMock(),
            "minimax": AsyncMock(),
        }

    @pytest.fixture
    def service(self, mock_providers):
        return LLMService(
            providers=mock_providers,
            default_provider="deepseek",
            fallback_chain=["glm", "minimax"],
        )

    @pytest.mark.asyncio
    async def test_invoke_primary_success(self, service, mock_providers):
        mock_providers["deepseek"].invoke = AsyncMock(return_value="DeepSeek response")
        result = await service.invoke([{"role": "user", "content": "Hello"}])
        assert result == "DeepSeek response"
        mock_providers["deepseek"].invoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invoke_with_fallback(self, service, mock_providers):
        mock_providers["deepseek"].invoke = AsyncMock(
            side_effect=LLMProviderError("deepseek", "rate limit")
        )
        mock_providers["glm"].invoke = AsyncMock(return_value="GLM response")

        result = await service.invoke([{"role": "user", "content": "Hello"}])

        assert result == "GLM response"
        # DeepSeek is retried max_retries (3) times before falling back
        assert mock_providers["deepseek"].invoke.call_count == 3
        mock_providers["glm"].invoke.assert_awaited_once()
        # minimax should not have been called
        mock_providers["minimax"].invoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invoke_all_providers_fail(self, service, mock_providers):
        mock_providers["deepseek"].invoke = AsyncMock(
            side_effect=LLMProviderError("deepseek", "timeout")
        )
        mock_providers["glm"].invoke = AsyncMock(
            side_effect=LLMProviderError("glm", "overloaded")
        )
        mock_providers["minimax"].invoke = AsyncMock(
            side_effect=LLMProviderError("minimax", "unauthorized")
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await service.invoke([{"role": "user", "content": "Hello"}])

        assert "All LLM providers failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invoke_skips_open_circuit(self, service, mock_providers):
        # Open the circuit for deepseek
        service._breakers["deepseek"] = CircuitBreaker(
            failure_threshold=2, recovery_timeout=60
        )
        service._breakers["deepseek"].record_failure()
        service._breakers["deepseek"].record_failure()

        mock_providers["deepseek"].invoke = AsyncMock(return_value="Should not be called")
        mock_providers["glm"].invoke = AsyncMock(return_value="GLM fallback")

        result = await service.invoke([{"role": "user", "content": "Hello"}])

        assert result == "GLM fallback"
        mock_providers["deepseek"].invoke.assert_not_awaited()
        mock_providers["glm"].invoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invoke_prompt_string(self, service, mock_providers):
        """invoke should accept a plain string prompt and convert to messages."""
        mock_providers["deepseek"].invoke = AsyncMock(return_value="OK")
        result = await service.invoke("Hello, how are you?")
        assert result == "OK"
        call_args = mock_providers["deepseek"].invoke.call_args[0][0]
        assert call_args == [{"role": "user", "content": "Hello, how are you?"}]

    @pytest.mark.asyncio
    async def test_invoke_records_success_resets_breaker(self, service, mock_providers):
        service._breakers["deepseek"].record_failure()
        assert service._breakers["deepseek"]._failure_count == 1

        mock_providers["deepseek"].invoke = AsyncMock(return_value="Success")
        await service.invoke([{"role": "user", "content": "Hi"}])

        assert service._breakers["deepseek"]._failure_count == 0

    @pytest.mark.asyncio
    async def test_invoke_custom_temperature(self, service, mock_providers):
        mock_providers["deepseek"].invoke = AsyncMock(return_value="OK")
        await service.invoke(
            [{"role": "user", "content": "Hi"}], temperature=0.7
        )
        call_kwargs = mock_providers["deepseek"].invoke.call_args[1]
        assert call_kwargs.get("temperature") == 0.7

    @pytest.mark.asyncio
    async def test_invoke_no_fallback_chain_raises_immediately(self, service, mock_providers):
        """When fallback_chain is empty, fail immediately on primary error."""
        service_no_fallback = LLMService(
            providers=mock_providers,
            default_provider="deepseek",
            fallback_chain=[],
        )
        mock_providers["deepseek"].invoke = AsyncMock(
            side_effect=LLMProviderError("deepseek", "error")
        )

        with pytest.raises(LLMProviderError):
            await service_no_fallback.invoke([{"role": "user", "content": "Hello"}])


# ---------------------------------------------------------------------------
# Provider adapter tests
# ---------------------------------------------------------------------------


class TestProviderAdapters:
    @pytest.mark.asyncio
    async def test_deepseek_provider_invoke(self):
        from app.services.llm_providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from DeepSeek"}}],
            "usage": {"total_tokens": 42},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await provider.invoke(
                [{"role": "user", "content": "Hi"}], temperature=0.5
            )

        assert result == "Hello from DeepSeek"
        mock_post.assert_awaited_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["model"] == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_provider_http_error(self):
        from app.services.llm_providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.invoke([{"role": "user", "content": "Hi"}])

        assert "deepseek" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_provider_network_error(self):
        from app.services.llm_providers.glm import GLMProvider

        provider = GLMProvider(
            api_key="test-key",
            base_url="https://open.bigmodel.cn/api/paas",
            model="glm-4-flash",
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection refused")
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.invoke([{"role": "user", "content": "Hi"}])

        assert "GLM" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_minimax_provider_default_model(self):
        from app.services.llm_providers.minimax import MiniMaxProvider

        provider = MiniMaxProvider(
            api_key="test-key", base_url="https://api.minimax.chat"
        )
        assert provider.model == "abab6.5s-chat"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "MiniMax response"}}],
            "usage": {"total_tokens": 10},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await provider.invoke([{"role": "user", "content": "Hi"}])

        assert result == "MiniMax response"
        assert mock_post.call_args[1]["json"]["model"] == "abab6.5s-chat"

    @pytest.mark.asyncio
    async def test_glm_provider_default_model(self):
        from app.services.llm_providers.glm import GLMProvider

        provider = GLMProvider(
            api_key="test-key", base_url="https://open.bigmodel.cn/api/paas"
        )
        assert provider.model == "glm-4-flash"

    @pytest.mark.asyncio
    async def test_deepseek_provider_default_model(self):
        from app.services.llm_providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key="test-key", base_url="https://api.deepseek.com"
        )
        assert provider.model == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_provider_chat_completions_url(self):
        from app.services.llm_providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await provider.invoke([{"role": "user", "content": "Hi"}])

        called_url = mock_post.call_args[0][0]
        assert called_url == "https://api.deepseek.com/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_provider_passes_auth_header(self):
        from app.services.llm_providers.glm import GLMProvider

        provider = GLMProvider(
            api_key="sk-glm-test-key",
            base_url="https://open.bigmodel.cn/api/paas",
            model="glm-4-flash",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}],
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            await provider.invoke([{"role": "user", "content": "Hi"}])

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-glm-test-key"


# ---------------------------------------------------------------------------
# LLMService integration-style tests
# ---------------------------------------------------------------------------


class TestLLMServiceBackoffAndRetry:
    @pytest.fixture
    def mock_providers(self):
        return {
            "deepseek": AsyncMock(),
            "glm": AsyncMock(),
        }

    @pytest.fixture
    def service(self, mock_providers):
        return LLMService(
            providers=mock_providers,
            default_provider="deepseek",
            fallback_chain=["glm"],
        )

    @pytest.mark.asyncio
    async def test_retry_transient_failure_then_succeed(self, service, mock_providers):
        """Provider should retry on transient errors before falling back."""
        call_count = [0]

        async def flaky_invoke(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise LLMProviderError("deepseek", "transient timeout")
            return "Success after retries"

        mock_providers["deepseek"].invoke = AsyncMock(side_effect=flaky_invoke)

        result = await service.invoke([{"role": "user", "content": "Hello"}])

        assert result == "Success after retries"
        assert call_count[0] == 3
        mock_providers["glm"].invoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retry_exhausted_then_fallback(self, service, mock_providers):
        """When retries are exhausted on primary, should fall back."""
        mock_providers["deepseek"].invoke = AsyncMock(
            side_effect=LLMProviderError("deepseek", "persistent error")
        )
        mock_providers["glm"].invoke = AsyncMock(return_value="GLM saves the day")

        result = await service.invoke([{"role": "user", "content": "Hello"}])

        assert result == "GLM saves the day"
        # deepseek should have been retried max_retries times
        assert mock_providers["deepseek"].invoke.call_count == 3
        mock_providers["glm"].invoke.assert_awaited_once()
