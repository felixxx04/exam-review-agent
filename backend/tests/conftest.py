import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock

from app.db.database import get_db
from app.db.models import Base
from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


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
async def client_with_db(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm_service():
    """Mock LLMService that returns safe dummy responses."""
    mock = AsyncMock()
    mock.invoke = AsyncMock(return_value=(
        '[{"question":"测试问题",'
        '"options":["A. 选项1","B. 选项2","C. 选项3","D. 选项4"],'
        '"correct":"B",'
        '"explanation":"测试解释",'
        '"source_chunk_ids":["chunk-1"]}]'
    ))
    return mock


@pytest.fixture
def mock_retrieval_service():
    """Mock RetrievalService that returns fake search results."""
    from app.services.retrieval_service import SearchResult

    mock = AsyncMock()
    mock.search = AsyncMock(return_value=[
        SearchResult(
            text="测试内容",
            score=0.9,
            metadata={"source": "test.pdf", "page": 1},
        )
    ])
    return mock
