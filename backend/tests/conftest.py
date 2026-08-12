import gc
import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Tests must never inherit developer credentials or persistent data paths.
_test_data_dir = tempfile.TemporaryDirectory(prefix="exam-review-agent-tests-")
os.environ.update(
    {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://127.0.0.1:6379/15",
        "CHROMA_PERSIST_DIR": os.path.join(_test_data_dir.name, "chroma"),
        "DEEPSEEK_API_KEY": "",
        "MINIMAX_API_KEY": "",
        "GLM_API_KEY": "",
        "ARK_API_KEY": "",
        "DEFAULT_LLM_PROVIDER": "deepseek",
        "JWT_SECRET": "test-only-secret-with-at-least-32-chars",
        "HF_ENDPOINT": "",
    }
)

from app.api.dependencies import get_object_storage  # noqa: E402
from app.core.auth import AuthenticatedUser, get_current_user  # noqa: E402
from app.core.middleware import RateLimitMiddleware  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.db.models import Base, User  # noqa: E402
from app.main import app  # noqa: E402
from app.repositories.mistakes import SqlAlchemyMistakeRepository  # noqa: E402
from app.services.object_storage import (  # noqa: E402
    ObjectStorageError,
    PresignedGet,
    StoredObject,
)


class InMemoryObjectStorage:
    """Test-only object storage implementation for API and service tests."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[tuple[str, str | None]] = []
        self.fail_delete = False

    async def put_file(
        self,
        *,
        key: str,
        source: Path,
        size_bytes: int,
        content_type: str,
        sha256: str,
    ) -> StoredObject:
        content = source.read_bytes()
        assert len(content) == size_bytes
        assert hashlib.sha256(content).hexdigest() == sha256
        self.objects[key] = content
        return StoredObject(
            key=key,
            size_bytes=size_bytes,
            etag="in-memory-etag",
            version_id="in-memory-version",
        )

    async def download_to_path(
        self,
        *,
        key: str,
        destination: Path,
        version_id: str | None = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.objects[key])

    async def delete_object(self, *, key: str, version_id: str | None = None) -> None:
        if self.fail_delete:
            raise ObjectStorageError(
                "Object storage is temporarily unavailable",
                "OBJECT_STORAGE_UNAVAILABLE",
            )
        self.deleted.append((key, version_id))
        self.objects.pop(key, None)

    async def presign_get(
        self,
        *,
        key: str,
        filename: str,
        content_type: str,
        disposition: str,
        expires_in_seconds: int,
        version_id: str | None = None,
    ) -> PresignedGet:
        return PresignedGet(
            url=f"https://storage.example.test/{key}",
            expires_in_seconds=expires_in_seconds,
        )


@pytest.fixture
def object_storage():
    storage = InMemoryObjectStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_object_storage, None)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    yield

    from chromadb.api.client import SharedSystemClient

    SharedSystemClient.clear_system_cache()
    gc.collect()
    _test_data_dir.cleanup()


@pytest.fixture
async def client():
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=1,
        username="test_user",
        role="user",
        session_id="test-session",
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def authenticated_user(db_session):
    user = User(
        username="test_user",
        email=None,
        hashed_password="test-password-hash",
        display_name="Test User",
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def client_with_db(db_session, authenticated_user, object_storage):
    user_id = authenticated_user.id
    username = authenticated_user.username
    role = authenticated_user.role

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    def current_user_override() -> AuthenticatedUser:
        # Avoid async lazy loading from FastAPI's synchronous dependency worker
        # after a test commits the ORM fixture, while preserving deliberate
        # in-test changes such as elevating the role to administrator.
        return AuthenticatedUser(
            id=user_id,
            username=authenticated_user.__dict__.get("username", username),
            role=authenticated_user.__dict__.get("role", role),
            session_id="test-session",
        )

    app.dependency_overrides[get_current_user] = current_user_override
    RateLimitMiddleware.reset()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    RateLimitMiddleware.reset()


@pytest.fixture
def mistake_repository(db_session, authenticated_user):
    return SqlAlchemyMistakeRepository(db_session)


@pytest.fixture
def mock_llm_service():
    """Mock LLMService that returns safe dummy responses."""
    mock = AsyncMock()
    mock.invoke = AsyncMock(
        return_value=(
            '[{"question":"测试问题",'
            '"options":["A. 选项1","B. 选项2","C. 选项3","D. 选项4"],'
            '"correct":"B",'
            '"explanation":"测试解释",'
            '"source_chunk_ids":["chunk-1"]}]'
        )
    )
    return mock


@pytest.fixture
def mock_retrieval_service():
    """Mock RetrievalService that returns fake search results."""
    from app.services.retrieval_service import SearchResult

    mock = AsyncMock()
    mock.search = AsyncMock(
        return_value=[
            SearchResult(
                text="测试内容",
                score=0.9,
                metadata={"source": "test.pdf", "page": 1},
            )
        ]
    )
    return mock
