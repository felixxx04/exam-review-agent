from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models import Material, User


@dataclass(frozen=True)
class QuotaUsage:
    file_limit: int
    files_used: int
    storage_limit_bytes: int
    storage_used_bytes: int


class QuotaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_usage(self, user_id: int) -> QuotaUsage:
        user = await self.db.get(User, user_id)
        if user is None:
            raise AppException("Resource not found", "NOT_FOUND")
        return await self._usage_for(user)

    async def ensure_upload_allowed(self, user_id: int, file_size: int) -> QuotaUsage:
        user = await self.lock_upload(user_id)
        usage = await self._usage_for(user)
        if (
            usage.files_used + 1 > usage.file_limit
            or usage.storage_used_bytes + file_size > usage.storage_limit_bytes
        ):
            raise AppException("Upload quota exceeded", "QUOTA_EXCEEDED")
        return usage

    async def ensure_file_slot_available(self, user_id: int) -> QuotaUsage:
        user = await self.lock_upload(user_id)
        usage = await self._usage_for(user)
        if usage.files_used + 1 > usage.file_limit:
            raise AppException("Upload quota exceeded", "QUOTA_EXCEEDED")
        return usage

    async def ensure_reserved_storage_allowed(
        self, user_id: int, file_size: int
    ) -> QuotaUsage:
        user = await self.lock_upload(user_id)
        usage = await self._usage_for(user)
        if usage.storage_used_bytes + file_size > usage.storage_limit_bytes:
            raise AppException("Upload quota exceeded", "QUOTA_EXCEEDED")
        return usage

    async def lock_upload(self, user_id: int) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise AppException("Resource not found", "NOT_FOUND")
        if user.is_disabled:
            raise AppException(
                "Account deletion is in progress",
                "ACCOUNT_DELETION_IN_PROGRESS",
            )
        return user

    async def _usage_for(self, user: User) -> QuotaUsage:
        result = await self.db.execute(
            select(
                func.count(Material.id),
                func.coalesce(func.sum(Material.file_size), 0),
            ).where(Material.user_id == user.id)
        )
        files_used, storage_used_bytes = result.one()
        return QuotaUsage(
            file_limit=user.file_limit,
            files_used=int(files_used),
            storage_limit_bytes=user.storage_limit_bytes,
            storage_used_bytes=int(storage_used_bytes),
        )
