from sqlalchemy import event, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.config import settings


TENANT_USER_ID_KEY = "tenant_user_id"


@event.listens_for(Session, "after_begin")
def _set_tenant_context_after_begin(
    session: Session,
    _transaction: object,
    connection: Connection,
) -> None:
    user_id = session.info.get(TENANT_USER_ID_KEY)
    if user_id is None or connection.dialect.name != "postgresql":
        return
    connection.execute(
        text("SELECT set_config('app.current_user_id', :user_id, true)"),
        {"user_id": str(user_id)},
    )


async def bind_tenant_context(session: AsyncSession, user_id: str | int) -> None:
    """Bind a trusted tenant ID to the current and future session transactions."""
    session.sync_session.info[TENANT_USER_ID_KEY] = str(user_id)
    if (
        session.get_bind().dialect.name == "postgresql"
        and session.in_transaction()
    ):
        await session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    return {"connect_args": {"timeout": 30}}


def to_sync_database_url(database_url: str) -> str:
    """Return the synchronous driver URL used by Alembic."""
    url = make_url(database_url)
    driver_by_backend = {
        "postgresql": "postgresql+psycopg",
        "sqlite": "sqlite+pysqlite",
    }
    drivername = driver_by_backend.get(url.get_backend_name())
    if drivername is None:
        return database_url
    return url.set(drivername=drivername).render_as_string(hide_password=False)


engine = create_async_engine(
    settings.database_url,
    echo=False,
    **_engine_kwargs(settings.database_url),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
