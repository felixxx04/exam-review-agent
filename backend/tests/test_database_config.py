from app.db.database import _engine_kwargs


def test_sqlite_engine_waits_for_busy_database():
    kwargs = _engine_kwargs("sqlite+aiosqlite:///./dev.db")

    assert kwargs["connect_args"]["timeout"] >= 30


def test_non_sqlite_engine_uses_default_kwargs():
    assert _engine_kwargs("postgresql+asyncpg://user:pass@localhost/db") == {}
