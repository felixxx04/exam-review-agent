"""Materials API endpoints for file upload, list, delete, and reprocess."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import FileType, Material, ProcessingStatus
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


@router.post("", response_model=MaterialResponse)
async def upload_material(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    if file.filename is None:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    file_type = _check_file_type(file.filename)
    content = await file.read()
    file_size = len(content)

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
        processing_status=ProcessingStatus.PENDING,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    return material


@router.get("", response_model=MaterialListResponse)
async def list_materials(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Material).order_by(Material.created_at.desc())
    )
    materials = result.scalars().all()
    return MaterialListResponse(
        materials=list(materials),
        total=len(materials),
    )


@router.get("/{material_id}", response_model=MaterialResponse)
async def get_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
):
    material = await db.get(Material, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="材料不存在")
    return material


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

    await db.delete(material)
    await db.commit()

    return {"detail": "已删除"}


@router.post("/{material_id}/reprocess", response_model=MaterialResponse)
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

    return material
