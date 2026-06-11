"""ARQ worker setup with Redis connection from application settings."""

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings


async def get_redis_settings() -> RedisSettings:
    """Build Redis settings from the application configuration."""
    # Support both full redis:// URLs and host:port pairs
    redis_url = settings.redis_url
    if redis_url.startswith("redis://"):
        return RedisSettings.from_dsn(redis_url)
    # Default: parse host and port
    host = "localhost"
    port = 6379
    if "://" in redis_url:
        _, rest = redis_url.split("://", 1)
    else:
        rest = redis_url
    if "@" in rest:
        _, rest = rest.split("@", 1)
    if ":" in rest:
        host, port_str = rest.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            port = 6379
    else:
        host = rest or host
    return RedisSettings(host=host, port=port)


class WorkerConfig:
    """Configuration holder for the ARQ worker."""

    # Functions exposed to the ARQ worker
    functions: list = []
    redis_settings: RedisSettings | None = None

    @classmethod
    async def initialize(cls) -> None:
        """Initialize the worker configuration."""
        cls.redis_settings = await get_redis_settings()
        # Discover and register task functions
        from app.tasks.parse_material import parse_material
        cls.functions = [parse_material]

    @classmethod
    async def get_pool(cls):
        """Get or create a Redis connection pool for enqueuing tasks."""
        if cls.redis_settings is None:
            await cls.initialize()
        return await create_pool(cls.redis_settings)
