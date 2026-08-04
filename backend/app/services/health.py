from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class ReadinessProbe(Protocol):
    name: str

    async def check(self) -> None: ...


class DatabaseReadinessProbe:
    name = "database"

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def check(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))


class RedisReadinessProbe:
    name = "redis"

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url

    async def check(self) -> None:
        client = Redis.from_url(
            self._redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()
