from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.common import ApiResponse
from app.schemas.memory import LearningProfileResponse
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/profile")
async def get_memory_profile(db: AsyncSession = Depends(get_db)):
    service = MemoryService(db)
    profile = await service.get_or_create_learning_profile(user_id="default")
    return ApiResponse.ok(data=LearningProfileResponse.model_validate(profile))
