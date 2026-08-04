from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories.mistakes import MistakeRepository, SqlAlchemyMistakeRepository


def get_mistake_repository(
    db: AsyncSession = Depends(get_db),
) -> MistakeRepository:
    return SqlAlchemyMistakeRepository(db)
