"""Materials API endpoints for file upload, list, delete, and reprocess."""

from __future__ import annotations

import datetime
import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import FileType, Material, MaterialChunk, ProcessingStatus
from app.schemas.common import ApiResponse
from app.schemas.materials import MaterialListResponse, MaterialResponse

router = APIRouter(prefix="/api/materials", tags=["materials"])

ALLOWED_TYPES = {
    "application/pdf": FileType.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileType.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileType.PPTX,
}

UPLOAD_DIR = Path("uploads")


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


@router.post("")
async def upload_material(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    file_type = _check_file_type(file.filename)
    content = await file.read()
    file_size = len(content)
    file_hash = hashlib.sha256(content).hexdigest()

    if file_size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({settings.max_upload_size_mb}MB)",
        )

    storage_name = f"{uuid.uuid4().hex}_{file.filename}"
    UPLOAD_DIR.mkdir(exist_ok=True)
    file_path = UPLOAD_DIR / storage_name
    file_path.write_bytes(content)

    material = Material(
        user_id=1,
        filename=storage_name,
        original_filename=file.filename,
        file_type=file_type,
        file_size=file_size,
        storage_path=str(file_path),
        mime_type=file.content_type,
        hash=file_hash,
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    # Inline processing (async workers are not available without Redis)
    try:
        material.processing_status = ProcessingStatus.PROCESSING
        await db.commit()

        from app.services.parser_service import ParserService

        parser = ParserService()
        result = await parser.parse(
            str(file_path),
            file_type=file_type.value if hasattr(file_type, "value") else file_type,
        )

        # Index chunks
        from dataclasses import asdict

        from app.services.retrieval_service import RetrievalService

        retrieval = RetrievalService()
        chunk_payloads = [asdict(c) for c in result.chunks]
        chunk_ids = await retrieval.index_chunks(
            user_id="default",
            chunks=chunk_payloads,
        )
        for chunk_id, chunk in zip(chunk_ids, chunk_payloads, strict=False):
            metadata = chunk.get("metadata", {}) or {}
            db.add(
                MaterialChunk(
                    material_id=material.id,
                    chunk_id=chunk_id,
                    text_preview=(chunk.get("text") or "")[:300],
                    page_number=metadata.get("page"),
                    token_count=len(chunk.get("text") or ""),
                    embedding_id=chunk_id,
                )
            )

        material.processing_status = ProcessingStatus.READY
        material.chunk_count = len(result.chunks)
        material.page_count = result.page_count
        material.processed_at = datetime.datetime.now(datetime.UTC)
    except Exception as exc:
        material.processing_status = ProcessingStatus.FAILED
        material.error_message = str(exc)[:200]
        material.parse_error = str(exc)[:500]
    finally:
        await db.commit()
        await db.refresh(material)

    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


@router.get("")
async def list_materials(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Material).order_by(Material.created_at.desc())
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
    db: AsyncSession = Depends(get_db),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    return ApiResponse.ok(data=MaterialResponse.model_validate(material))


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")

    file_path = UPLOAD_DIR / material.filename
    if file_path.exists():
        file_path.unlink()

    await db.execute(delete(MaterialChunk).where(MaterialChunk.material_id == material_id))
    await db.delete(material)
    await db.commit()

    return ApiResponse.ok(data={"detail": "已删除"})


@router.post("/{material_id}/reprocess")
async def reprocess_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")

    material.processing_status = ProcessingStatus.PENDING
    material.error_message = None
    await db.commit()
    await db.refresh(material)

    return ApiResponse.ok(data=MaterialResponse.model_validate(material))
