"""Materials API endpoints for file upload, list, delete, and reprocess."""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.db.models import FileType, Material, MaterialChunk, ProcessingStatus
from app.schemas.common import ApiResponse
from app.schemas.materials import MaterialListResponse, MaterialResponse
from app.services.course_service import CourseService
from app.services.quota_service import QuotaService

router = APIRouter(prefix="/api/materials", tags=["materials"])

ALLOWED_TYPES = {
    "application/pdf": FileType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileType.PPTX,
}

UPLOAD_DIR = Path("uploads")
UPLOAD_CHUNK_SIZE = 1024 * 1024
logger = logging.getLogger(__name__)


def _lexical_tokens(text: str) -> str:
    tokens = re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text.lower())
    return " ".join(tokens)


def _check_file_type(filename: str) -> FileType:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return FileType.PDF
    elif ext in (".docx", ".doc"):
        return FileType.DOCX
    elif ext in (".pptx", ".ppt"):
        return FileType.PPTX
    raise HTTPException(
        status_code=400,
        detail=f"不支持的文件类型: {ext}。支持的类型: PDF, DOCX, PPTX",
    )


async def _write_upload(file: UploadFile, destination: Path) -> tuple[int, str]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    maximum_size = settings.max_upload_size_mb * 1024 * 1024
    file_size = 0
    file_hash = hashlib.sha256()
    try:
        with destination.open("xb") as staged:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > maximum_size:
                    raise HTTPException(
                        status_code=400,
                        detail=(f"文件大小超过限制 ({settings.max_upload_size_mb}MB)"),
                    )
                file_hash.update(chunk)
                staged.write(chunk)
        return file_size, file_hash.hexdigest()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


async def _discard_reservation(
    db: AsyncSession, material_id: int, file_path: Path
) -> None:
    file_path.unlink(missing_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, 3):
        await db.rollback()
        try:
            material = await db.scalar(
                select(Material).where(Material.id == material_id)
            )
            if material is not None:
                await db.delete(material)
            await db.commit()
            return
        except Exception as exc:
            last_error = exc
            logger.exception(
                "Failed to discard upload reservation material_id=%s attempt=%s",
                material_id,
                attempt,
            )

    await db.rollback()
    assert last_error is not None
    raise last_error


@router.post("")
async def upload_material(
    file: UploadFile,
    course_id: int | None = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    course = await CourseService(db).resolve_course(current_user.id, course_id)
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    file_type = _check_file_type(file.filename)
    safe_filename = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
    storage_name = f"{uuid.uuid4().hex}_{safe_filename}"
    file_path = UPLOAD_DIR / storage_name
    await QuotaService(db).ensure_file_slot_available(current_user.id)

    material = Material(
        user_id=current_user.id,
        course_id=course.id,
        filename=storage_name,
        original_filename=file.filename,
        file_type=file_type,
        file_size=0,
        storage_path=str(file_path),
        mime_type=file.content_type,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    try:
        await QuotaService(db).lock_upload(current_user.id)
        file_size, file_hash = await _write_upload(file, file_path)
        await QuotaService(db).ensure_reserved_storage_allowed(
            current_user.id, file_size
        )
        material.file_size = file_size
        material.hash = file_hash
        await db.commit()
        await db.refresh(material)
        await QuotaService(db).lock_upload(current_user.id)
    except Exception:
        await _discard_reservation(db, material.id, file_path)
        raise

    # Inline processing (async workers are not available without Redis)
    try:
        material.processing_status = ProcessingStatus.PROCESSING
        await db.flush()

        from app.services.parser_service import ParserService

        parser = ParserService()
        result = await parser.parse(
            str(file_path),
            file_type=file_type.value if hasattr(file_type, "value") else file_type,
        )

        # Index chunks
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
        chunk_ids = await retrieval.index_chunks(
            user_id=current_user.subject,
            chunks=chunk_payloads,
            course_id=course.id,
        )
        for chunk_id, chunk in zip(chunk_ids, chunk_payloads, strict=False):
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

        material.processing_status = ProcessingStatus.READY
        material.chunk_count = len(normalized_chunks)
        material.page_count = result.page_count
        material.processed_at = datetime.datetime.now(datetime.UTC)
    except SQLAlchemyError:
        await db.rollback()
        raise
    except Exception as exc:
        material.processing_status = ProcessingStatus.FAILED
        material.error_message = str(exc)[:200]
        material.parse_error = str(exc)[:500]
    try:
        await db.commit()
        await db.refresh(material)
    except SQLAlchemyError:
        await db.rollback()
        raise

    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


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
        )
        .order_by(Material.created_at.desc())
    )
    materials = result.scalars().all()
    response = MaterialListResponse(
        materials=list(materials),
        total=len(materials),
    )
    return ApiResponse.ok(data=response, meta={"total": len(materials)})


@router.get("/{material_id}")
async def get_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    material = (
        await db.execute(
            select(Material).where(
                Material.id == material_id,
                Material.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    material = (
        await db.execute(
            select(Material).where(
                Material.id == material_id,
                Material.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")

    file_path = UPLOAD_DIR / material.filename
    if file_path.exists():
        file_path.unlink()

    chunk_rows = await db.execute(
        select(MaterialChunk.chunk_id).where(MaterialChunk.material_id == material_id)
    )
    chunk_ids = list(chunk_rows.scalars().all())
    if chunk_ids:
        from app.services.retrieval_service import RetrievalService

        await RetrievalService().delete_chunks(
            user_id=current_user.subject,
            chunk_ids=chunk_ids,
            course_id=material.course_id,
        )

    await db.execute(
        delete(MaterialChunk).where(MaterialChunk.material_id == material_id)
    )
    await db.delete(material)
    await db.commit()

    return ApiResponse.ok(data={"detail": "已删除"})


@router.post("/{material_id}/reprocess")
async def reprocess_material(
    material_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    material = (
        await db.execute(
            select(Material).where(
                Material.id == material_id,
                Material.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")

    material.processing_status = ProcessingStatus.PENDING
    material.error_message = None
    await db.commit()
    await db.refresh(material)

    return ApiResponse.ok(data=MaterialResponse.model_validate(material))
