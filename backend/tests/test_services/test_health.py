from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from app.services.health import DatabaseReadinessProbe, RedisReadinessProbe


@pytest.mark.asyncio
async def test_database_probe_executes_select_one():
    connection = AsyncMock()
    connection_context = AsyncMock()
    connection_context.__aenter__.return_value = connection
    engine = Mock()
    engine.connect.return_value = connection_context

    await DatabaseReadinessProbe(engine).check()

    statement = connection.execute.await_args.args[0]
    assert str(statement) == "SELECT 1"


@pytest.mark.asyncio
async def test_redis_probe_pings_and_closes_client(monkeypatch):
    client = AsyncMock()
    from_url = Mock(return_value=client)
    monkeypatch.setattr("app.services.health.Redis.from_url", from_url)

    await RedisReadinessProbe("redis://localhost:6379/15").check()

    from_url.assert_called_once_with(
        "redis://localhost:6379/15",
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    client.ping.assert_awaited_once()
    client.aclose.assert_awaited_once()
