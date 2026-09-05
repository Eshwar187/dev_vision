import urllib.parse
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import (
    get_current_active_user,
    require_workspace_member,
    verify_csrf_token,
)
from app.core.database import get_db
from app.core.exceptions import FileTooLargeException, ValidationException
from app.core.storage import get_storage
from app.modules.documents.schemas import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.modules.documents.service import DocumentService
from app.modules.documents.validator import MAX_FILE_SIZE_DEFAULT
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMembership

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf_token)],
    summary="Upload a new document to workspace",
)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Uploads a document (PDF, TXT, Markdown, or DOCX) to the specified workspace.
    Synchronously enforces bounded reading, file signatures, and per-workspace deduplication.
    """
    if not file.filename:
        raise ValidationException("Uploaded file must have a filename.")

    # Bounded stream consumption: Read up to MAX_FILE_SIZE_DEFAULT + 1 byte
    # Content-Length is checked if present, but actual consumed bytes are authoritative
    chunk_size = 64 * 1024
    buffer = bytearray()

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > MAX_FILE_SIZE_DEFAULT:
            raise FileTooLargeException(
                f"File size exceeds maximum permitted limit of {MAX_FILE_SIZE_DEFAULT // (1024 * 1024)} MB."
            )

    file_bytes = bytes(buffer)

    document = await DocumentService.upload_document(
        db=db,
        workspace_id=workspace_id,
        user_id=current_user.id,
        raw_filename=file.filename,
        file_bytes=file_bytes,
    )

    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List workspace documents with cursor pagination",
)
async def list_documents(
    workspace_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """
    Retrieves documents belonging to the workspace using stable cursor pagination
    ordered by created_at DESC, id DESC.
    """
    items, next_cursor = await DocumentService.list_documents(
        db=db,
        workspace_id=workspace_id,
        limit=limit,
        cursor=cursor,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(doc) for doc in items],
        next_cursor=next_cursor,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Retrieve document metadata",
)
async def get_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """
    Retrieves document metadata for a single document strictly scoped to workspace.
    """
    document = await DocumentService.get_document(
        db=db,
        workspace_id=workspace_id,
        document_id=document_id,
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "/{document_id}/download",
    summary="Download document binary file via streaming proxy",
)
async def download_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Streams the document binary from S3 through FastAPI.
    Enforces authentication, workspace scoping, and secure content disposition headers.
    """
    document = await DocumentService.get_document(
        db=db,
        workspace_id=workspace_id,
        document_id=document_id,
    )

    storage = get_storage()
    stream = storage.get_object_stream(document.object_key)

    # Safe RFC 6266 / RFC 5987 content-disposition header
    safe_ascii_name = document.original_filename.encode("ascii", "ignore").decode("ascii") or "document"
    utf8_filename = urllib.parse.quote(document.original_filename, safe="")

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_ascii_name}"; filename*=UTF-8\'\'{utf8_filename}',
        "Content-Length": str(document.file_size),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-cache, no-store, must-revalidate",
    }

    def stream_generator():
        # Stream chunks directly from botocore stream
        for chunk in stream.iter_chunks(chunk_size=64 * 1024):
            yield chunk

    return StreamingResponse(
        content=stream_generator(),
        media_type=document.mime_type,
        headers=headers,
    )


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    dependencies=[Depends(verify_csrf_token)],
    summary="Delete a document from workspace",
)
async def delete_document(
    workspace_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> DocumentDeleteResponse:
    """
    Deletes a document from storage and metadata database.
    Enforces RBAC: Owner/Admin can delete any document; Member can only delete their own.
    """
    await DocumentService.delete_document(
        db=db,
        workspace_id=workspace_id,
        document_id=document_id,
        user_id=current_user.id,
        user_role=membership.role,
    )
    return DocumentDeleteResponse()
