"""ARQ worker settings and the Redis delivery pool."""

from __future__ import annotations

from arq import create_pool, cron
from arq.connections import RedisSettings

from app.core.config import settings


def _redis_settings() -> RedisSettings:
    redis_url = settings.redis_url
    if redis_url.startswith("redis://"):
        return RedisSettings.from_dsn(redis_url)
    host = "localhost"
    port = 6379
    if "://" in redis_url:
        _, rest = redis_url.split("://", 1)
    else:
        rest = redis_url
    if "@" in rest:
        _, rest = rest.split("@", 1)
    if ":" in rest:
        host, port_text = rest.rsplit(":", 1)
        try:
            port = int(port_text)
        except ValueError:
            pass
    else:
        host = rest or host
    return RedisSettings(host=host, port=port)


async def get_redis_settings() -> RedisSettings:
    """Build Redis settings from the application configuration."""
    return _redis_settings()


class WorkerSettings:
    """ARQ's importable worker configuration."""

    from app.tasks.parse_material import process_material_job, recover_material_jobs

    functions = [process_material_job]
    cron_jobs = [
        cron(
            recover_material_jobs,
            name="recover_material_jobs",
            job_id="material-job-recovery",
            minute={0, 15, 30, 45},
            timeout=60,
            keep_result=0,
        )
    ]
    redis_settings = _redis_settings()


class WorkerConfig:
    """Compatibility holder used by API-side enqueue calls."""

    functions = WorkerSettings.functions
    cron_jobs = WorkerSettings.cron_jobs
    redis_settings = WorkerSettings.redis_settings

    @classmethod
    async def initialize(cls) -> None:
        cls.redis_settings = await get_redis_settings()

    @classmethod
    async def get_pool(cls):
        if cls.redis_settings is None:
            await cls.initialize()
        return await create_pool(cls.redis_settings)
