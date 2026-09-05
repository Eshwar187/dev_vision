import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import delete, desc, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    AuthorizationException,
    DocumentNotFoundException,
    DuplicateDocumentException,
    ExternalServiceException,
    ValidationException,
)
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.modules.documents.models import Document
from app.modules.documents.validator import sanitize_filename, validate_file_content

logger = get_logger("documents.service")


def encode_cursor(created_at: datetime, doc_id: uuid.UUID) -> str:
    """Encodes created_at and document ID into an opaque base64 cursor."""
    payload = {
        "t": created_at.isoformat(),
        "id": str(doc_id),
    }
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor_str: str) -> Tuple[datetime, uuid.UUID]:
    """Decodes and validates an opaque base64 cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        dt = datetime.fromisoformat(payload["t"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        doc_id = uuid.UUID(payload["id"])
        return dt, doc_id
    except Exception as exc:
        raise ValidationException("Invalid cursor parameter.") from exc


class DocumentService:
    """
    Manages document lifecycle, S3 object storage operations,
    PostgreSQL metadata, and compensating rollback workflows.
    """

    @staticmethod
    async def upload_document(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        raw_filename: str,
        file_bytes: bytes,
    ) -> Document:
        """
        Validates content, normalizes filename, uploads binary to S3 first,
        and inserts metadata into PostgreSQL.
        Executes compensating S3 deletion if database insertion fails.
        """
        storage = get_storage()

        # 1. Filename sanitization & normalization
        safe_filename, ext = sanitize_filename(raw_filename)

        # 2. Content validation & MIME detection
        canonical_mime = validate_file_content(file_bytes, ext)
        file_size = len(file_bytes)

        # 3. Synchronous SHA-256 calculation
        checksum = hashlib.sha256(file_bytes).hexdigest()

        # 4. Fast application-level duplicate pre-check in the same workspace
        existing_doc = await db.scalar(
            select(Document).where(
                Document.workspace_id == workspace_id,
                Document.checksum == checksum,
            ).limit(1)
        )
        if existing_doc:
            raise DuplicateDocumentException(
                message=f"A document with identical content already exists in this workspace (id: {existing_doc.id}, filename: '{existing_doc.original_filename}').",
                details={
                    "existing_document_id": str(existing_doc.id),
                    "original_filename": existing_doc.original_filename,
                    "checksum": checksum,
                },
            )

        # 5. Generate server-controlled object key
        doc_id = uuid.uuid4()
        checksum_prefix = checksum[:6]
        object_key = (
            f"workspaces/{workspace_id}/documents/{doc_id}/{checksum_prefix}/{doc_id}.{ext}"
        )

        # 6. Upload object to S3 / MinIO
        try:
            storage.upload_bytes(
                key=object_key,
                data=file_bytes,
                content_type=canonical_mime,
            )
        except Exception as exc:
            logger.error(
                "S3 upload failed",
                workspace_id=str(workspace_id),
                object_key=object_key,
                error=str(exc),
            )
            raise ExternalServiceException(
                "Failed to upload document binary to storage. Please try again later."
            ) from exc

        # 7. Insert PostgreSQL document metadata record
        document = Document(
            id=doc_id,
            workspace_id=workspace_id,
            uploaded_by=user_id,
            original_filename=safe_filename,
            object_key=object_key,
            mime_type=canonical_mime,
            file_size=file_size,
            checksum=checksum,
            status="uploaded",
        )

        db.add(document)
        try:
            await db.flush()
            await db.commit()
            await db.refresh(document)
            logger.info(
                "Document uploaded successfully",
                document_id=str(document.id),
                workspace_id=str(workspace_id),
                file_size=file_size,
            )
            return document
        except IntegrityError as exc:
            await db.rollback()
            # Compensating action: delete newly uploaded S3 object
            try:
                storage.delete_object(object_key)
                logger.info("Compensated S3 object deletion on DB collision", object_key=object_key)
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to delete orphaned S3 object during rollback",
                    object_key=object_key,
                    error=str(cleanup_exc),
                )

            # Check if this was a unique constraint violation on (workspace_id, checksum)
            err_str = str(exc.orig) if hasattr(exc, "orig") else str(exc)
            if "uq_documents_workspace_checksum" in err_str or "checksum" in err_str:
                raise DuplicateDocumentException(
                    message="A document with identical content was concurrently uploaded to this workspace.",
                    details={"checksum": checksum},
                ) from exc

            raise ExternalServiceException("Database integrity error during document creation.") from exc

        except Exception as exc:
            await db.rollback()
            # Compensating action: delete newly uploaded S3 object
            try:
                storage.delete_object(object_key)
                logger.info("Compensated S3 object deletion on DB error", object_key=object_key)
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to delete orphaned S3 object during rollback",
                    object_key=object_key,
                    error=str(cleanup_exc),
                )
            raise ExternalServiceException("Failed to commit document metadata.") from exc

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Document], Optional[str]]:
        """
        Lists documents scoped to workspace using keyset cursor pagination.
        Ordered by created_at DESC, id DESC.
        """
        query = (
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(desc(Document.created_at), desc(Document.id))
        )

        if cursor:
            cursor_time, cursor_id = decode_cursor(cursor)
            # Row-value comparison for stable keyset pagination: (created_at, id) < (cursor_time, cursor_id)
            query = query.where(
                or_(
                    Document.created_at < cursor_time,
                    and_clause := (
                        (Document.created_at == cursor_time) & (Document.id < cursor_id)
                    ),
                )
            )

        # Fetch limit + 1 to check if another page exists
        query = query.limit(limit + 1)
        result = await db.execute(query)
        items = list(result.scalars().all())

        next_cursor = None
        if len(items) > limit:
            extra_item = items.pop()  # Remove the extra (limit + 1)-th item
            # The last item in the returned page serves as the anchor for next_cursor
            last_item = items[-1]
            next_cursor = encode_cursor(last_item.created_at, last_item.id)

        return items, next_cursor

    @staticmethod
    async def get_document(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> Document:
        """
        Retrieves a document strictly scoped to workspace.
        Returns Document or raises DocumentNotFoundException.
        """
        document = await db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.workspace_id == workspace_id,
            )
        )
        if not document:
            raise DocumentNotFoundException()
        return document

    @staticmethod
    async def delete_document(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> None:
        """
        Enforces deletion RBAC:
        - Owner/Admin can delete any document in workspace.
        - Member can only delete documents they personally uploaded.
        Executes S3-first deletion: if S3 delete fails, DB record is preserved.
        """
        storage = get_storage()
        document = await DocumentService.get_document(db, workspace_id, document_id)

        # RBAC Check
        if user_role not in ("owner", "admin"):
            if document.uploaded_by != user_id:
                raise AuthorizationException(
                    "Members can only delete documents they personally uploaded."
                )

        # 1. S3-First: Delete S3 object
        try:
            storage.delete_object(document.object_key)
        except Exception as exc:
            logger.error(
                "S3 deletion failed. Preserving DB record.",
                document_id=str(document_id),
                object_key=document.object_key,
                error=str(exc),
            )
            raise ExternalServiceException(
                "Failed to delete document from storage. Operation aborted to prevent orphaned data."
            ) from exc

        # 2. Delete database record
        try:
            await db.execute(delete(Document).where(Document.id == document_id))
            await db.commit()
            logger.info(
                "Document deleted successfully",
                document_id=str(document_id),
                workspace_id=str(workspace_id),
            )
        except Exception as exc:
            await db.rollback()
            logger.error(
                "Failed to delete document metadata after S3 deletion",
                document_id=str(document_id),
                error=str(exc),
            )
            raise ExternalServiceException("Failed to delete document database record.") from exc
