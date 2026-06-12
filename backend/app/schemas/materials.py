"""Material schemas for request/response serialization."""

from datetime import datetime

from pydantic import BaseModel


class MaterialResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    page_count: int
    processing_status: str
    chunk_count: int | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MaterialListResponse(BaseModel):
    materials: list[MaterialResponse]
    total: int
