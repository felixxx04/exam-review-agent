from __future__ import annotations

import asyncio
import datetime
import hashlib
import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_object_storage
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.core.exceptions import AppException
from app.db.database import get_db
from app.db.models import Material, MaterialChunk, ProcessingStatus, StorageStatus
from app.schemas.common import ApiResponse
from app.schemas.materials import (
    MaterialAccessUrlResponse,
    MaterialListResponse,
    MaterialResponse,
)
from app.services.course_service import CourseService
from app.services.material_upload_validation import (
    MaterialUploadValidationError,
    infer_material_file_type,
    validate_material_upload,
)
from app.services.material_storage_cleanup import (
    delete_legacy_material,
    delete_material_chunks,
    is_processing_lease_active,
)
from app.services.object_storage import (
    ObjectStorage,
    ObjectStorageError,
    StoredObject,
    build_material_object_key,
)
from app.services.quota_service import QuotaService


router = APIRouter(prefix="/api/materials", tags=["materials"])

UPLOAD_CHUNK_SIZE = 1024 * 1024
LEGACY_UPLOAD_ROOT = Path("uploads")
INDEXING_LEASE_DURATION = datetime.timedelta(hours=1)
logger = logging.getLogger(__name__)


def _lexical_tokens(text: str) -> str:
    import re

    tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower())
    return " ".join(tokens)


def _display_filename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def _indexing_lease_expires_at() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + INDEXING_LEASE_DURATION


async def _stage_upload(file: UploadFile, destination: Path) -> tuple[int, str]:
    maximum_size = settings.max_upload_size_mb * 1024 * 1024
    file_size = 0
    file_hash = hashlib.sha256()
    try:
        with destination.open("xb") as staged:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > maximum_size:
                    raise MaterialUploadValidationError(
                        "File size exceeds the allowed limit", "FILE_TOO_LARGE"
                    )
                file_hash.update(chunk)
                staged.write(chunk)
        return file_size, file_hash.hexdigest()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


async def _discard_reservation(
    db: AsyncSession,
    material_id: int,
    *,
    storage: ObjectStorage | None = None,
    delete_object: bool = False,
    object_version_id: str | None = None,
    object_size_bytes: int | None = None,
    object_sha256: str | None = None,
    uncertain_object_write: bool = False,
) -> None:
    """Remove a failed reservation, retaining metadata when remote cleanup fails."""
    await db.rollback()
    material = await db.scalar(
        select(Material).where(
            Material.id == material_id,
            Material.storage_status == StorageStatus.RESERVED,
        )
    )
    if material is not None:
        if object_version_id is not None:
            material.object_version_id = object_version_id
        if object_size_bytes is not None:
            material.file_size = object_size_bytes
        if object_sha256 is not None:
            material.hash = object_sha256
        if uncertain_object_write:
            # A timed-out PUT can still become visible after a negative HEAD.
            # Keep the server-generated key until recovery can retry cleanup.
            material.storage_status = StorageStatus.DELETING
            material.object_write_uncertain = True
            material.error_message = "Material cleanup is pending"
            await db.commit()
            return
        if delete_object and material.object_key is not None:
            if storage is None:
                raise RuntimeError("Object storage is required to discard an object")
            try:
                await storage.delete_object(
                    key=material.object_key,
                    version_id=object_version_id or material.object_version_id,
                )
            except ObjectStorageError:
                material.storage_status = StorageStatus.DELETING
                material.error_message = "Material cleanup is pending"
                await db.commit()
                raise

    last_error: Exception | None = None
    for attempt in range(1, 3):
        await db.rollback()
        try:
            material = await db.scalar(
                select(Material).where(
                    Material.id == material_id,
                    Material.storage_status == StorageStatus.RESERVED,
                )
            )
            if material is not None:
                await db.delete(material)
            await db.commit()
            return
        except Exception as exc:
            last_error = exc
            logger.exception(
                "Failed to discard material reservation material_id=%s attempt=%s",
                material_id,
                attempt,
            )

    await db.rollback()
    assert last_error is not None
    raise last_error


async def _settle_object_upload(
    upload_task: asyncio.Task[StoredObject],
) -> StoredObject | None:
    """Wait for an uncancellable storage operation before compensating it."""
    while not upload_task.done():
        try:
            await asyncio.shield(upload_task)
        except asyncio.CancelledError:
            continue
        except Exception:
            return None
    try:
        return upload_task.result()
    except BaseException:
        return None


async def _delete_legacy_material(material: Material) -> None:
    await delete_legacy_material(material, upload_root=LEGACY_UPLOAD_ROOT)


async def _find_duplicate_material(
    db: AsyncSession,
    *,
    user_id: int,
    course_id: int,
    sha256: str,
    excluding_material_id: int,
) -> Material | None:
    return await db.scalar(
        select(Material).where(
            Material.user_id == user_id,
            Material.course_id == course_id,
            Material.hash == sha256,
            Material.id != excluding_material_id,
            Material.storage_status.in_(
                [StorageStatus.RESERVED, StorageStatus.AVAILABLE]
            ),
        )
    )


async def _get_owned_material(
    db: AsyncSession,
    *,
    material_id: int,
    user_id: int,
    include_deleting: bool = False,
    lock: bool = False,
) -> Material | None:
    statement = select(Material).where(
        Material.id == material_id,
        Material.user_id == user_id,
    )
    if not include_deleting:
        statement = statement.where(
            Material.storage_status.notin_(
                [StorageStatus.DELETING, StorageStatus.DELETED]
            )
        )
    if lock:
        statement = statement.with_for_update()
    return await db.scalar(statement)


@router.post("")
async def upload_material(
    file: UploadFile,
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    course = await CourseService(db).resolve_course(current_user.id, course_id)
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    display_filename = _display_filename(file.filename)
    file_type = infer_material_file_type(display_filename)
    object_id = uuid.uuid4().hex
    await QuotaService(db).ensure_file_slot_available(current_user.id)
    material = Material(
        user_id=current_user.id,
        course_id=course.id,
        filename=object_id,
        original_filename=display_filename,
        file_type=file_type,
        file_size=0,
        object_id=object_id,
        storage_backend="s3",
        storage_status=StorageStatus.RESERVED,
        mime_type=file.content_type,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(material)
    await db.flush()
    material.object_key = build_material_object_key(
        user_id=current_user.id,
        course_id=course.id,
        material_id=material.id,
        object_id=object_id,
    )
    material_id = material.id
    await db.commit()

    suffix = Path(display_filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="exam-review-upload-") as temp_dir:
        staged_path = Path(temp_dir) / f"material-{material_id}{suffix}"
        try:
            # Keep the Task 1.4 user lock through staging and the S3 transition.
            # A deletion request either wins before this point (and disables the user),
            # or waits until this upload reaches a durable terminal state.
            await QuotaService(db).lock_upload(current_user.id)
            file_size, file_hash = await _stage_upload(file, staged_path)
            validated = validate_material_upload(
                staged_path,
                filename=display_filename,
                declared_content_type=file.content_type,
                max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
                max_archive_uncompressed_bytes=(
                    settings.max_archive_uncompressed_mb * 1024 * 1024
                ),
            )
        except Exception:
            await _discard_reservation(db, material_id)
            raise
        except BaseException:
            await asyncio.shield(_discard_reservation(db, material_id))
            raise

        stored: StoredObject | None = None
        upload_task: asyncio.Task[StoredObject] | None = None
        upload_started = False
        try:
            await QuotaService(db).ensure_reserved_storage_allowed(
                current_user.id, file_size
            )
            material = await _get_owned_material(
                db,
                material_id=material_id,
                user_id=current_user.id,
                lock=True,
            )
            if material is None:
                raise AppException(
                    "Account deletion is in progress", "ACCOUNT_DELETION_IN_PROGRESS"
                )
            duplicate = await _find_duplicate_material(
                db,
                user_id=current_user.id,
                course_id=course.id,
                sha256=file_hash,
                excluding_material_id=material_id,
            )
            if duplicate is not None:
                await _discard_reservation(db, material_id)
                raise AppException(
                    "An identical material already exists", "DUPLICATE_MATERIAL"
                )

            material.file_size = file_size
            material.hash = file_hash
            material.mime_type = validated.content_type

            # Make the reservation's real quota metadata durable before any
            # remote write. A crash after this commit is recoverable without
            # undercounting storage usage.
            await db.commit()
            await QuotaService(db).lock_upload(current_user.id)
            material = await _get_owned_material(
                db,
                material_id=material_id,
                user_id=current_user.id,
                lock=True,
            )
            if material is None:
                raise AppException(
                    "Account deletion is in progress", "ACCOUNT_DELETION_IN_PROGRESS"
                )
            upload_started = True
            upload_task = asyncio.create_task(
                storage.put_file(
                    key=material.object_key or "",
                    source=staged_path,
                    size_bytes=file_size,
                    content_type=validated.content_type,
                    sha256=file_hash,
                )
            )
            stored = await asyncio.shield(upload_task)
            material.object_version_id = stored.version_id
            material.object_etag = stored.etag
            material.object_write_uncertain = False
            material.storage_status = StorageStatus.AVAILABLE
            await db.commit()
            await db.refresh(material)
        except AppException as exc:
            if exc.code != "DUPLICATE_MATERIAL":
                await _discard_reservation(
                    db,
                    material_id,
                    storage=storage,
                    delete_object=upload_started,
                    object_version_id=(
                        stored.version_id if stored is not None else None
                    ),
                    object_size_bytes=file_size,
                    object_sha256=file_hash,
                    uncertain_object_write=upload_started and stored is None,
                )
            raise
        except Exception:
            await _discard_reservation(
                db,
                material_id,
                storage=storage,
                delete_object=upload_started,
                object_version_id=stored.version_id if stored is not None else None,
                object_size_bytes=file_size,
                object_sha256=file_hash,
                uncertain_object_write=upload_started and stored is None,
            )
            raise
        except BaseException:
            if upload_task is not None:
                settled = await _settle_object_upload(upload_task)
                if settled is not None:
                    stored = settled
            cleanup = _discard_reservation(
                db,
                material_id,
                storage=storage,
                delete_object=upload_started,
                object_version_id=stored.version_id if stored is not None else None,
                object_size_bytes=file_size,
                object_sha256=file_hash,
                uncertain_object_write=upload_started and stored is None,
            )
            cleanup_task = asyncio.create_task(cleanup)
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                try:
                    await cleanup_task
                except Exception:
                    logger.exception(
                        "Could not compensate cancelled material upload material_id=%s",
                        material_id,
                    )
                raise
            raise

        # Keep the deletion/upload lock until indexing reaches a durable terminal
        # state, so account cleanup cannot finish before this upload's vectors.
        await QuotaService(db).lock_upload(current_user.id)
        await _process_material(
            db,
            storage=storage,
            material=material,
            user_subject=current_user.subject,
            course_id=course.id,
        )
        await db.refresh(material)
    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


async def _process_material(
    db: AsyncSession,
    *,
    storage: ObjectStorage,
    material: Material,
    user_subject: str,
    course_id: int,
) -> None:
    material_id = material.id
    lease_id = uuid.uuid4().hex
    retrieval = None
    indexed_chunk_ids: list[str] = []
    indexing_intent_persisted = False
    try:
        material.processing_status = ProcessingStatus.PROCESSING
        material.processing_lease_expires_at = _indexing_lease_expires_at()
        material.processing_lease_id = lease_id
        await db.flush()
        with tempfile.TemporaryDirectory(prefix="exam-review-parse-") as temp_dir:
            suffix = Path(material.original_filename).suffix.lower()
            source_path = Path(temp_dir) / f"material-{material.id}{suffix}"
            await storage.download_to_path(
                key=material.object_key or "",
                destination=source_path,
                version_id=material.object_version_id,
            )

            from app.services.parser_service import ParserService

            result = await ParserService().parse(
                str(source_path),
                file_type=material.file_type,
            )

        from dataclasses import asdict

        from app.services.chunking_service import ChunkingService
        from app.services.retrieval_service import RetrievalService

        retrieval = RetrievalService()
        normalized_chunks = ChunkingService().normalize(result.chunks)
        chunk_payloads = []
        for chunk in normalized_chunks:
            payload = asdict(chunk)
            metadata = payload.get("metadata", {}) or {}
            payload["metadata"] = {
                **metadata,
                "source": material.original_filename,
                "original_filename": material.original_filename,
                "storage_filename": material.filename,
                "material_id": material.id,
            }
            chunk_payloads.append(payload)
        indexed_chunk_ids = [str(uuid.uuid4()) for _ in chunk_payloads]
        if indexed_chunk_ids:
            _add_material_chunk_intent(
                db,
                material=material,
                chunk_payloads=chunk_payloads,
                chunk_ids=indexed_chunk_ids,
            )
            # Commit the IDs before the external index write. If this process
            # stops anywhere below, recovery can delete every possible chunk.
            await db.commit()
            indexing_intent_persisted = True
            # Reacquire and retain the Task 1.4 user serialization lock across
            # the non-transactional index write and its final material state.
            # Course, account, material-delete, and recovery paths take the
            # same lock before removing a material's durable cleanup intent.
            await QuotaService(db).lock_upload(material.user_id)
            material = await _reload_owned_processing_attempt(
                db,
                material_id=material_id,
                user_id=material.user_id,
                lease_id=lease_id,
                chunk_ids=indexed_chunk_ids,
            )
            if material is None:
                await db.rollback()
                return
            await retrieval.index_chunks(
                user_id=user_subject,
                chunks=chunk_payloads,
                course_id=course_id,
                chunk_ids=indexed_chunk_ids,
            )

        if indexed_chunk_ids:
            marked_ready = await _mark_processing_attempt_ready(
                db,
                material_id=material_id,
                lease_id=lease_id,
                chunk_count=len(normalized_chunks),
                page_count=result.page_count,
            )
            if not marked_ready:
                await db.rollback()
                await _compensate_indexed_chunks(
                    retrieval,
                    material_id=material_id,
                    user_subject=user_subject,
                    course_id=course_id,
                    chunk_ids=indexed_chunk_ids,
                )
                return
        else:
            material.processing_status = ProcessingStatus.READY
            material.chunk_count = len(normalized_chunks)
            material.page_count = result.page_count
            material.processed_at = datetime.datetime.now(datetime.UTC)
            material.processing_lease_expires_at = None
            material.processing_lease_id = None
    except asyncio.CancelledError:
        await db.rollback()
        if indexing_intent_persisted:
            await _fail_indexing_intent(
                db,
                retrieval=retrieval,
                material_id=material_id,
                user_subject=user_subject,
                course_id=course_id,
                chunk_ids=indexed_chunk_ids,
                lease_id=lease_id,
            )
        raise
    except SQLAlchemyError:
        await db.rollback()
        if indexing_intent_persisted:
            await _fail_indexing_intent(
                db,
                retrieval=retrieval,
                material_id=material_id,
                user_subject=user_subject,
                course_id=course_id,
                chunk_ids=indexed_chunk_ids,
                lease_id=lease_id,
            )
        raise
    except Exception:
        if indexing_intent_persisted:
            await _fail_indexing_intent(
                db,
                retrieval=retrieval,
                material_id=material_id,
                user_subject=user_subject,
                course_id=course_id,
                chunk_ids=indexed_chunk_ids,
                lease_id=lease_id,
            )
            return
        material.processing_status = ProcessingStatus.FAILED
        material.error_message = "Material processing failed"
        material.parse_error = "Material processing failed"
        material.processing_lease_expires_at = None
        material.processing_lease_id = None
        try:
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            raise
        return

    try:
        await db.commit()
    except BaseException:
        await db.rollback()
        if indexing_intent_persisted:
            await _fail_indexing_intent(
                db,
                retrieval=retrieval,
                material_id=material_id,
                user_subject=user_subject,
                course_id=course_id,
                chunk_ids=indexed_chunk_ids,
                lease_id=lease_id,
            )
        raise


def _add_material_chunk_intent(
    db: AsyncSession,
    *,
    material: Material,
    chunk_payloads: list[dict],
    chunk_ids: list[str],
) -> None:
    for chunk_id, chunk in zip(chunk_ids, chunk_payloads, strict=True):
        metadata = chunk.get("metadata", {}) or {}
        chunk_text = chunk.get("text") or ""
        db.add(
            MaterialChunk(
                material_id=material.id,
                user_id=material.user_id,
                course_id=material.course_id,
                chunk_id=chunk_id,
                content=chunk_text,
                text_preview=chunk_text[:300],
                page_number=metadata.get("page"),
                token_count=len(chunk_text),
                content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                lexical_tokens=_lexical_tokens(chunk_text),
                chunk_metadata=metadata,
                embedding_id=chunk_id,
            )
        )


async def _reload_owned_processing_attempt(
    db: AsyncSession,
    *,
    material_id: int,
    user_id: int,
    lease_id: str,
    chunk_ids: list[str],
) -> Material | None:
    """Lock and validate a processing attempt after an external-work boundary."""
    material = await db.scalar(
        select(Material)
        .where(Material.id == material_id, Material.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        material is None
        or material.storage_status != StorageStatus.AVAILABLE
        or material.processing_status != ProcessingStatus.PROCESSING
        or material.processing_lease_id != lease_id
        or not is_processing_lease_active(material.processing_lease_expires_at)
    ):
        return None
    if not chunk_ids:
        return material

    persisted_ids = set(
        (
            await db.scalars(
                select(MaterialChunk.chunk_id).where(
                    MaterialChunk.material_id == material_id,
                )
            )
        ).all()
    )
    return material if persisted_ids == set(chunk_ids) else None


async def _mark_processing_attempt_ready(
    db: AsyncSession,
    *,
    material_id: int,
    lease_id: str,
    chunk_count: int,
    page_count: int,
) -> bool:
    """Commit READY only if this worker still owns the same attempt token."""
    result = await db.execute(
        update(Material)
        .where(
            Material.id == material_id,
            Material.storage_status == StorageStatus.AVAILABLE,
            Material.processing_status == ProcessingStatus.PROCESSING,
            Material.processing_lease_id == lease_id,
        )
        .values(
            processing_status=ProcessingStatus.READY,
            chunk_count=chunk_count,
            page_count=page_count,
            processed_at=datetime.datetime.now(datetime.UTC),
            processing_lease_expires_at=None,
            processing_lease_id=None,
        )
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1


async def _fail_indexing_intent(
    db: AsyncSession,
    *,
    retrieval,
    material_id: int,
    user_subject: str,
    course_id: int,
    chunk_ids: list[str],
    lease_id: str,
) -> None:
    """Persist retryable cleanup before compensating an uncertain index write."""
    await db.rollback()
    material = await db.scalar(
        select(Material).where(Material.id == material_id).with_for_update()
    )
    if material is None:
        await _compensate_indexed_chunks(
            retrieval,
            material_id=material_id,
            user_subject=user_subject,
            course_id=course_id,
            chunk_ids=chunk_ids,
        )
        return
    if material.processing_status == ProcessingStatus.READY:
        # The final commit may have reached the database before its acknowledgement
        # failed. This token proves this is our completed attempt, so its vectors
        # remain authoritative.
        return
    if (
        material.storage_status != StorageStatus.AVAILABLE
        or material.processing_status != ProcessingStatus.PROCESSING
        or material.processing_lease_id != lease_id
    ):
        await _compensate_indexed_chunks(
            retrieval,
            material_id=material_id,
            user_subject=user_subject,
            course_id=course_id,
            chunk_ids=chunk_ids,
        )
        return

    material.processing_status = ProcessingStatus.FAILED
    material.error_message = "Material index cleanup is pending"
    material.parse_error = "Material processing failed"
    material.processing_lease_expires_at = None
    material.processing_lease_id = None
    try:
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        return

    if not await _compensate_indexed_chunks(
        retrieval,
        material_id=material_id,
        user_subject=user_subject,
        course_id=course_id,
        chunk_ids=chunk_ids,
    ):
        return

    try:
        await db.execute(
            delete(MaterialChunk).where(
                MaterialChunk.material_id == material_id,
                MaterialChunk.chunk_id.in_(chunk_ids),
            )
        )
        material.error_message = "Material processing failed"
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()


async def _compensate_indexed_chunks(
    retrieval,
    *,
    material_id: int,
    user_subject: str,
    course_id: int,
    chunk_ids: list[str],
) -> bool:
    if retrieval is None or not chunk_ids:
        return not chunk_ids
    try:
        await retrieval.delete_chunks(
            user_id=user_subject,
            chunk_ids=chunk_ids,
            course_id=course_id,
        )
    except Exception:
        logger.exception(
            "Could not compensate indexed material chunks material_id=%s", material_id
        )
        return False
    return True


@router.get("")
async def list_materials(
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).resolve_course(current_user.id, course_id)
    result = await db.execute(
        select(Material)
        .where(
            Material.user_id == current_user.id,
            Material.course_id == course.id,
            Material.storage_status.notin_(
                [StorageStatus.DELETING, StorageStatus.DELETED]
            ),
        )
        .order_by(Material.created_at.desc())
    )
    materials = result.scalars().all()
    response = MaterialListResponse(materials=list(materials), total=len(materials))
    return ApiResponse.ok(data=response, meta={"total": len(materials)})


@router.get("/{material_id}/access-url")
async def get_material_access_url(
    material_id: int,
    response: Response,
    disposition: str = "inline",
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    material = await _get_owned_material(
        db,
        material_id=material_id,
        user_id=current_user.id,
        lock=True,
    )
    if (
        material is None
        or material.storage_status != StorageStatus.AVAILABLE
        or material.object_key is None
    ):
        raise HTTPException(status_code=404, detail="材料不存在")
    access = await storage.presign_get(
        key=material.object_key,
        filename=material.original_filename,
        content_type=material.mime_type or "application/octet-stream",
        disposition=disposition,
        expires_in_seconds=settings.s3_presigned_url_ttl_seconds,
        version_id=material.object_version_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return ApiResponse.ok(
        data=MaterialAccessUrlResponse(
            url=access.url,
            expires_in_seconds=access.expires_in_seconds,
        )
    )


@router.get("/{material_id}")
async def get_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    material = await _get_owned_material(
        db,
        material_id=material_id,
        user_id=current_user.id,
    )
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    await QuotaService(db).lock_upload(current_user.id)
    material = await _get_owned_material(
        db,
        material_id=material_id,
        user_id=current_user.id,
        include_deleting=True,
        lock=True,
    )
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    if material.storage_status == StorageStatus.DELETED:
        return ApiResponse.ok(data={"detail": "已删除"})
    if (
        material.storage_status == StorageStatus.RESERVED
        or material.object_write_uncertain
    ):
        await db.rollback()
        raise ObjectStorageError(
            "Material cleanup is pending", "OBJECT_STORAGE_UNAVAILABLE"
        )
    if (
        material.processing_status == ProcessingStatus.PROCESSING
        and is_processing_lease_active(material.processing_lease_expires_at)
    ):
        await db.rollback()
        raise AppException("Material processing is in progress", "CONFLICT")

    material.storage_status = StorageStatus.DELETING
    material.processing_lease_id = None
    material.processing_lease_expires_at = None
    material.error_message = "Material cleanup is pending"
    await db.commit()

    try:
        if material.storage_backend == "legacy_local":
            await _delete_legacy_material(material)
        elif material.object_key is not None:
            await storage.delete_object(
                key=material.object_key,
                version_id=material.object_version_id,
            )
        else:
            raise ObjectStorageError(
                "Material storage metadata is unavailable", "OBJECT_STORAGE_UNAVAILABLE"
            )
    except ObjectStorageError:
        raise

    try:
        await delete_material_chunks(db, material=material)
    except Exception:
        await db.rollback()
        raise
    material.storage_status = StorageStatus.DELETED
    material.error_message = None
    await db.commit()
    return ApiResponse.ok(data={"detail": "已删除"})


@router.post("/{material_id}/reprocess")
async def reprocess_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await QuotaService(db).lock_upload(current_user.id)
    material = await _get_owned_material(
        db,
        material_id=material_id,
        user_id=current_user.id,
    )
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    if (
        material.processing_status == ProcessingStatus.PROCESSING
        and is_processing_lease_active(material.processing_lease_expires_at)
    ):
        await db.rollback()
        raise AppException("Material processing is in progress", "CONFLICT")
    persisted_chunk_ids = list(
        (
            await db.scalars(
                select(MaterialChunk.chunk_id).where(
                    MaterialChunk.material_id == material.id
                )
            )
        ).all()
    )
    if persisted_chunk_ids and material.processing_status != ProcessingStatus.READY:
        await db.rollback()
        raise AppException("Material index cleanup is pending", "CONFLICT")

    if persisted_chunk_ids:
        # Persist a recoverable intent before removing external vectors. A crash
        # after deletion must not leave a ready material with missing vectors.
        lease_id = uuid.uuid4().hex
        material.processing_status = ProcessingStatus.PROCESSING
        material.processing_lease_expires_at = _indexing_lease_expires_at()
        material.processing_lease_id = lease_id
        material.error_message = "Material index cleanup is pending"
        try:
            await db.commit()
            await QuotaService(db).lock_upload(current_user.id)
            material = await _reload_owned_processing_attempt(
                db,
                material_id=material_id,
                user_id=current_user.id,
                lease_id=lease_id,
                chunk_ids=persisted_chunk_ids,
            )
            if material is None:
                await db.rollback()
                raise AppException("Material processing attempt is stale", "CONFLICT")
        except BaseException:
            await db.rollback()
            raise
        try:
            await delete_material_chunks(db, material=material)
        except BaseException:
            await db.rollback()
            raise

    material.processing_status = ProcessingStatus.PENDING
    material.error_message = None
    material.parse_error = None
    material.processing_lease_expires_at = None
    material.processing_lease_id = None
    try:
        await db.commit()
    except BaseException:
        await db.rollback()
        raise
    await db.refresh(material)
    return ApiResponse.ok(data=MaterialResponse.model_validate(material))
