from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from pathlib import Path

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import bind_tenant_context
from app.db.models import (
    Material,
    MaterialChunk,
    ProcessingStatus,
    StorageStatus,
    User,
)
from app.services.object_storage import ObjectStorage, ObjectStorageError


logger = logging.getLogger(__name__)
LEGACY_UPLOAD_ROOT = Path("uploads")


@dataclass(frozen=True)
class ReservationRecoveryReport:
    scanned: int
    objects_cleaned: int
    tombstones_written: int
    pending: int


def _legacy_material_path(material: Material, *, upload_root: Path) -> Path:
    root = upload_root.resolve()
    if material.storage_path:
        candidate = Path(material.storage_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
    else:
        candidate = root / material.filename
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ObjectStorageError(
            "Material storage metadata is unavailable", "OBJECT_STORAGE_UNAVAILABLE"
        )
    return resolved


async def delete_legacy_material(
    material: Material,
    *,
    upload_root: Path | None = None,
) -> None:
    path = _legacy_material_path(
        material,
        upload_root=upload_root or LEGACY_UPLOAD_ROOT,
    )
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except OSError as exc:
        raise ObjectStorageError(
            "Object storage is temporarily unavailable", "OBJECT_STORAGE_UNAVAILABLE"
        ) from exc


async def delete_material_chunks(
    db: AsyncSession,
    *,
    material: Material,
) -> None:
    """Remove a material's index entries before deleting their durable IDs."""
    chunk_rows = await db.execute(
        select(MaterialChunk.chunk_id).where(MaterialChunk.material_id == material.id)
    )
    chunk_ids = list(chunk_rows.scalars().all())
    if chunk_ids:
        from app.services.retrieval_service import RetrievalService

        await RetrievalService().delete_chunks(
            user_id=str(material.user_id),
            chunk_ids=chunk_ids,
            course_id=material.course_id,
        )
    await db.execute(
        delete(MaterialChunk).where(MaterialChunk.material_id == material.id)
    )


def is_processing_lease_active(
    expires_at: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(UTC)
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at > now


async def _try_lock_material_owner(db: AsyncSession, *, user_id: int) -> bool:
    """Acquire the same user lock as upload and deletion without user-state checks."""
    owner_id = await db.scalar(
        select(User.id).where(User.id == user_id).with_for_update(skip_locked=True)
    )
    return owner_id is not None


async def _reload_recoverable_material(
    db: AsyncSession,
    *,
    material_id: int,
    now: datetime,
) -> Material | None:
    material = await db.scalar(
        select(Material).where(Material.id == material_id).with_for_update()
    )
    if material is None:
        return None
    if (
        material.processing_status == ProcessingStatus.PROCESSING
        and is_processing_lease_active(
            material.processing_lease_expires_at,
            now=now,
        )
    ):
        return None
    if material.storage_status in {StorageStatus.RESERVED, StorageStatus.DELETING}:
        return material
    if material.storage_status != StorageStatus.AVAILABLE:
        return None
    if material.processing_status == ProcessingStatus.PROCESSING:
        # A null lease exists on rows created before the lease migration and on
        # workers that stopped before persisting chunk intent. With no active
        # lease there is no live external write to protect, so move it back to
        # a retryable terminal state below.
        return material
    if material.processing_status != ProcessingStatus.FAILED:
        return None
    has_chunk_intent = await db.scalar(
        select(MaterialChunk.id)
        .where(MaterialChunk.material_id == material.id)
        .limit(1)
    )
    return material if has_chunk_intent is not None else None


async def recover_stale_material_reservations_for_user(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    user_id: int,
    older_than: datetime,
) -> ReservationRecoveryReport:
    """Run reservation recovery inside one trusted tenant scope.

    The application role is subject to PostgreSQL RLS, so maintenance must
    bind the operator-supplied tenant before scanning that user's rows. A
    later worker can call this same entrypoint when Task 2.2 adds scheduling.
    """
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    await bind_tenant_context(db, user_id)
    return await recover_stale_material_reservations(
        db,
        storage,
        older_than=older_than,
    )


async def recover_stale_material_reservations(
    db: AsyncSession,
    storage: ObjectStorage,
    *,
    older_than: datetime,
) -> ReservationRecoveryReport:
    """Compensate durable S3 reservations and incomplete material deletions.

    This is intentionally a small database-backed maintenance primitive. Task 2.2
    may schedule it from the worker, but the storage layer already exposes a safe,
    idempotent recovery operation for crashes in the upload window.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(Material)
        .where(
            Material.storage_backend.in_(["s3", "legacy_local"]),
            or_(
                Material.storage_status.in_(
                    [StorageStatus.RESERVED, StorageStatus.DELETING]
                ),
                and_(
                    Material.storage_status == StorageStatus.AVAILABLE,
                    or_(
                        and_(
                            Material.processing_status == ProcessingStatus.FAILED,
                            Material.id.in_(select(MaterialChunk.material_id)),
                        ),
                        and_(
                            Material.processing_status == ProcessingStatus.PROCESSING,
                            or_(
                                Material.processing_lease_expires_at.is_(None),
                                Material.processing_lease_expires_at < now,
                            ),
                        ),
                    ),
                ),
            ),
            Material.created_at < older_than,
        )
        .order_by(Material.id)
    )
    materials = list(result.scalars().all())
    objects_cleaned = 0
    tombstones_written = 0
    pending = 0

    for candidate in materials:
        if not await _try_lock_material_owner(db, user_id=candidate.user_id):
            pending += 1
            continue
        material = await _reload_recoverable_material(
            db,
            material_id=candidate.id,
            now=now,
        )
        if material is None:
            await db.rollback()
            continue

        if material.storage_status == StorageStatus.AVAILABLE:
            try:
                await delete_material_chunks(db, material=material)
            except Exception:
                logger.exception(
                    "Could not clean stale material index intent material_id=%s",
                    material.id,
                )
                await db.rollback()
                pending += 1
                continue

            material.processing_status = ProcessingStatus.FAILED
            material.processing_lease_expires_at = None
            material.processing_lease_id = None
            material.error_message = "Material processing failed"
            material.parse_error = "Material processing failed"
            await db.commit()
            continue

        material.storage_status = StorageStatus.DELETING
        material.error_message = "Material cleanup is pending"
        await db.commit()

        try:
            if material.storage_backend == "legacy_local":
                await delete_legacy_material(material)
            elif material.object_key is not None:
                await storage.delete_object(
                    key=material.object_key,
                    version_id=material.object_version_id,
                )
            else:
                pending += 1
                continue
            objects_cleaned += 1
        except ObjectStorageError:
            pending += 1
            continue

        if not await _try_lock_material_owner(db, user_id=material.user_id):
            pending += 1
            continue
        current = await _reload_recoverable_material(
            db,
            material_id=material.id,
            now=now,
        )
        if current is None:
            await db.rollback()
            continue
        try:
            await delete_material_chunks(db, material=current)
        except Exception:
            logger.exception(
                "Could not clean material indexes material_id=%s", current.id
            )
            await db.rollback()
            pending += 1
            continue

        current.storage_status = StorageStatus.DELETED
        current.object_write_uncertain = False
        current.error_message = None
        await db.commit()
        tombstones_written += 1

    return ReservationRecoveryReport(
        scanned=len(materials),
        objects_cleaned=objects_cleaned,
        tombstones_written=tombstones_written,
        pending=pending,
    )
