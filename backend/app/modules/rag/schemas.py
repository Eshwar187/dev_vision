"""
DevVision AI - RAG Pydantic Request/Response Schemas.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class RagCitationOut(BaseModel):
    citation_marker: Union[int, str]
    document_id: Optional[uuid.UUID] = None
    chunk_id: Optional[uuid.UUID] = None
    document_name: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    excerpt: str
    rank: int
    score: float


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000, description="Natural language search or synthesis query")
    top_k: int = Field(default=5, ge=1, le=10, description="Number of context passages to retrieve")


class RagQueryResponse(BaseModel):
    query_id: uuid.UUID
    query_text: str
    answer: str
    has_unverified_claims: bool
    processing_time_ms: int
    citations: List[RagCitationOut]
    created_at: datetime


class RagHistoryItem(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    query_text: str
    answer: str
    has_unverified_claims: bool
    retrieval_chunks_count: int
    processing_time_ms: int
    created_at: datetime
    citations: List[RagCitationOut] = []


class RagHistoryResponse(BaseModel):
    items: List[RagHistoryItem]
    total: int


class ReindexResponse(BaseModel):
    document_id: uuid.UUID
    generation_id: Optional[uuid.UUID] = None
    status: str
    message: str


class DocumentChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    token_count: int
    generation_id: uuid.UUID
    created_at: datetime


class DocumentChunksResponse(BaseModel):
    document_id: uuid.UUID
    active_generation_id: Optional[uuid.UUID] = None
    total_chunks: int
    chunks: List[DocumentChunkOut]
