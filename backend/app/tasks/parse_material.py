"""Background task for parsing uploaded materials.

This defines the ``parse_material`` function which is enqueued as an
ARQ job after a file is uploaded. It orchestrates:

1. Updating material status to "processing"
2. Calling ParserService.parse() to extract text chunks
3. Indexing chunks in the vector store
4. Updating material status to "ready" or "failed"
"""

import logging
from typing import Optional

from app.core.exceptions import FileParsingError
from app.db.database import AsyncSessionLocal
from app.db.models import Material, ProcessingStatus
from app.services.parser_service import ParserService

logger = logging.getLogger(__name__)


async def parse_material(ctx: dict, material_id: int) -> None:
    """Parse an uploaded material file and index its content.

    Args:
        ctx: ARQ job context (contains Redis connection, etc.).
        material_id: The database ID of the Material record to process.

    Side effects:
        - Updates Material.processing_status to 'processing' then
          'ready' or 'failed'.
        - Stores parsed chunks in the vector store via
          ctx["vector_store"] if available.
    """
    parser = ParserService()

    # 1) Update material status to "processing"
    await _update_material_status(material_id, ProcessingStatus.PROCESSING, error_msg=None)

    try:
        # 2) Load the material record to get file path
        material = await _get_material(material_id)
        if material is None:
            logger.error("Material %d not found in database", material_id)
            return

        file_path = _build_file_path(material.filename)

        # 3) Parse the file
        result = await parser.parse(file_path, file_type=material.file_type.value if hasattr(material.file_type, 'value') else material.file_type)

        # 4) Index chunks into vector store
        await _index_chunks(ctx, material, result)

        # 5) Update material status to "ready"
        await _update_material_status(
            material_id,
            ProcessingStatus.READY,
            chunk_count=len(result.chunks),
            page_count=result.page_count,
        )

        logger.info(
            "Material %d (%s) parsed successfully: %d chunks",
            material_id,
            material.original_filename,
            len(result.chunks),
        )
        return result

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Failed to parse material %d: %s", material_id, error_msg)
        await _update_material_status(
            material_id,
            ProcessingStatus.FAILED,
            error_msg=error_msg,
        )
        raise FileParsingError(str(material_id), error_msg) from exc


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_material(material_id: int) -> Optional[Material]:
    """Fetch a Material record from the database."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Material).where(Material.id == material_id)
        )
        return result.scalar_one_or_none()


async def _update_material_status(
    material_id: int,
    status: ProcessingStatus,
    error_msg: Optional[str] = None,
    chunk_count: Optional[int] = None,
    page_count: Optional[int] = None,
) -> None:
    """Update a Material record's processing fields."""
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Material).where(Material.id == material_id)
        )
        material = result.scalar_one_or_none()
        if material is None:
            logger.warning("Material %d not found for status update", material_id)
            return

        material.processing_status = status  # type: ignore[assignment]
        if error_msg is not None:
            material.error_message = error_msg
        if chunk_count is not None:
            material.chunk_count = chunk_count
        if page_count is not None:
            material.page_count = page_count

        await session.commit()


def _build_file_path(filename: str) -> str:
    """Build the full file system path for an uploaded file.

    Uploaded files are stored under ./uploads/ relative to the project root.
    """
    import os
    uploads_dir = os.environ.get(
        "UPLOADS_DIR",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads"),
    )
    return os.path.join(uploads_dir, filename)
