import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    """Safe document metadata response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    original_filename: str
    mime_type: str
    file_size: int
    checksum: str
    status: str
    uploaded_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Cursor-paginated document list response."""

    items: List[DocumentResponse]
    next_cursor: Optional[str] = None


class DocumentDeleteResponse(BaseModel):
    """Response envelope for document deletion."""

    status: str = "success"
    message: str = "Document deleted successfully."
