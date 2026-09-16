import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CodebaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    repository_url: Optional[str] = Field(None, max_length=1024)
    default_branch: str = Field("main", max_length=255)


class CodebaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    repository_url: Optional[str] = None
    default_branch: str
    active_generation_id: Optional[uuid.UUID] = None
    is_indexed: bool
    created_at: datetime
    updated_at: datetime


class CodebaseListResponse(BaseModel):
    items: List[CodebaseResponse]
    total: int


class CodebaseGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codebase_id: uuid.UUID
    workspace_id: uuid.UUID
    generation_number: int
    status: str
    pipeline_version: str
    embedding_model_revision: str
    commit_hash: Optional[str] = None
    branch: Optional[str] = None
    total_files: int
    total_symbols: int
    total_chunks: int
    error_message: Optional[str] = None
    activated_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    created_at: datetime


class CodebaseFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_id: uuid.UUID
    file_path: str
    language: str
    content_hash: str
    byte_size: int
    line_count: int
    created_at: datetime


class CodebaseFileListResponse(BaseModel):
    items: List[CodebaseFileResponse]
    total: int
    next_cursor: Optional[str] = None


class CodebaseSymbolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_id: uuid.UUID
    file_id: uuid.UUID
    name: str
    symbol_type: str
    parent_symbol_id: Optional[uuid.UUID] = None
    start_line: int
    end_line: int
    signature: Optional[str] = None
    docstring: Optional[str] = None


class CodebaseSymbolListResponse(BaseModel):
    items: List[CodebaseSymbolResponse]
    total: int
    next_cursor: Optional[str] = None


class CodebaseRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    generation_id: uuid.UUID
    source_symbol_id: uuid.UUID
    target_symbol_id: Optional[uuid.UUID] = None
    relationship_type: str
    target_symbol_name: str
    target_file_path: Optional[str] = None
    line_number: int
    confidence: str


class CodebaseRelationshipListResponse(BaseModel):
    items: List[CodebaseRelationshipResponse]
    total: int


class CodebaseSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=50)


class CodebaseSearchResult(BaseModel):
    chunk_id: uuid.UUID
    file_path: str
    language: str
    start_line: int
    end_line: int
    scope_path: str
    content: str
    score: float
    retrieval_mode: str  # dense, sparse, or hybrid


class CodebaseSearchResponse(BaseModel):
    results: List[CodebaseSearchResult]
    total: int


class CodebaseQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(8, ge=1, le=20)


class CodebaseCitationResponse(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    snippet_preview: str
    citation_marker: str


class CodebaseQueryResponse(BaseModel):
    id: uuid.UUID
    query: str
    answer: str
    citations: List[CodebaseCitationResponse]
    retrieval_strategy: str
    latency_ms: int
    generation_id: uuid.UUID
    created_at: datetime
