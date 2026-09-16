import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    require_workspace_member,
    require_workspace_role,
    verify_csrf_token,
)
from app.core.exceptions import EntityNotFoundException, ValidationException
from app.modules.codebase.models import (
    Codebase,
    CodebaseFile,
    CodebaseIndexGeneration,
    CodebaseRelationship,
    CodebaseSymbol,
)
from app.modules.codebase.schemas import (
    CodebaseCitationResponse,
    CodebaseCreate,
    CodebaseFileListResponse,
    CodebaseFileResponse,
    CodebaseGenerationResponse,
    CodebaseListResponse,
    CodebaseQueryRequest,
    CodebaseQueryResponse,
    CodebaseRelationshipListResponse,
    CodebaseRelationshipResponse,
    CodebaseResponse,
    CodebaseSearchRequest,
    CodebaseSearchResponse,
    CodebaseSearchResult,
    CodebaseSymbolListResponse,
    CodebaseSymbolResponse,
)
from app.modules.codebase.service import CodebaseService
from app.modules.identity.models import User
from app.modules.workspaces.models import WorkspaceMembership

router = APIRouter()
_codebase_service_instance: Optional[CodebaseService] = None


def get_codebase_service() -> CodebaseService:
    global _codebase_service_instance
    if _codebase_service_instance is None:
        _codebase_service_instance = CodebaseService()
    return _codebase_service_instance


@router.post(
    "/{workspace_id}/codebases",
    response_model=CodebaseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf_token)],
)
async def create_codebase(
    workspace_id: uuid.UUID,
    payload: CodebaseCreate,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_role("owner", "admin")),
    service: CodebaseService = Depends(get_codebase_service),
):
    cb = await service.create_codebase(
        db,
        workspace_id=workspace_id,
        name=payload.name,
        repository_url=payload.repository_url,
        default_branch=payload.default_branch,
    )
    return cb


@router.get(
    "/{workspace_id}/codebases",
    response_model=CodebaseListResponse,
)
async def list_codebases(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
):
    items = await service.list_codebases(db, workspace_id)
    return CodebaseListResponse(items=items, total=len(items))


@router.get(
    "/{workspace_id}/codebases/{codebase_id}",
    response_model=CodebaseResponse,
)
async def get_codebase(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
):
    return await service.get_codebase(db, workspace_id, codebase_id)


@router.delete(
    "/{workspace_id}/codebases/{codebase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_csrf_token)],
)
async def delete_codebase(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_role("owner", "admin")),
    service: CodebaseService = Depends(get_codebase_service),
):
    await service.delete_codebase(db, workspace_id, codebase_id)
    return None


@router.post(
    "/{workspace_id}/codebases/{codebase_id}/upload",
    response_model=CodebaseGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_csrf_token)],
)
async def upload_codebase_archive(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_role("owner", "admin")),
    service: CodebaseService = Depends(get_codebase_service),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise ValidationException("Uploaded repository archive must be a .zip file.")

    archive_bytes = await file.read()
    gen = await service.index_archive(db, workspace_id, codebase_id, archive_bytes)
    return gen


@router.get(
    "/{workspace_id}/codebases/{codebase_id}/status",
    response_model=List[CodebaseGenerationResponse],
)
async def get_indexing_status(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
):
    await service.get_codebase(db, workspace_id, codebase_id)
    stmt = (
        select(CodebaseIndexGeneration)
        .where(
            CodebaseIndexGeneration.codebase_id == codebase_id,
            CodebaseIndexGeneration.workspace_id == workspace_id,
        )
        .order_by(CodebaseIndexGeneration.generation_number.desc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get(
    "/{workspace_id}/codebases/{codebase_id}/files",
    response_model=CodebaseFileListResponse,
)
async def list_codebase_files(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
    limit: int = Query(50, ge=1, le=200),
):
    cb = await service.get_codebase(db, workspace_id, codebase_id)
    if not cb.active_generation_id:
        return CodebaseFileListResponse(items=[], total=0, next_cursor=None)

    stmt = (
        select(CodebaseFile)
        .where(
            CodebaseFile.generation_id == cb.active_generation_id,
            CodebaseFile.codebase_id == codebase_id,
            CodebaseFile.workspace_id == workspace_id,
        )
        .order_by(CodebaseFile.file_path.asc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    files = list(res.scalars().all())
    return CodebaseFileListResponse(items=files, total=len(files), next_cursor=None)


@router.get(
    "/{workspace_id}/codebases/{codebase_id}/symbols",
    response_model=CodebaseSymbolListResponse,
)
async def list_codebase_symbols(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
    symbol_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    cb = await service.get_codebase(db, workspace_id, codebase_id)
    if not cb.active_generation_id:
        return CodebaseSymbolListResponse(items=[], total=0, next_cursor=None)

    stmt = select(CodebaseSymbol).where(
        CodebaseSymbol.generation_id == cb.active_generation_id,
        CodebaseSymbol.workspace_id == workspace_id,
    )
    if symbol_name:
        stmt = stmt.where(CodebaseSymbol.name.ilike(f"%{symbol_name}%"))

    stmt = stmt.order_by(CodebaseSymbol.name.asc()).limit(limit)
    res = await db.execute(stmt)
    symbols = list(res.scalars().all())
    return CodebaseSymbolListResponse(items=symbols, total=len(symbols), next_cursor=None)


@router.post(
    "/{workspace_id}/codebases/{codebase_id}/search",
    response_model=CodebaseSearchResponse,
)
async def search_codebase(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    payload: CodebaseSearchRequest,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    service: CodebaseService = Depends(get_codebase_service),
):
    cb = await service.get_codebase(db, workspace_id, codebase_id)
    if not cb.active_generation_id:
        return CodebaseSearchResponse(results=[], total=0)

    dense_candidates = await service.retriever.retrieve_dense(
        db, workspace_id, cb.active_generation_id, payload.query, limit=payload.top_k
    )
    sparse_candidates = await service.retriever.retrieve_sparse(
        db, workspace_id, cb.active_generation_id, payload.query, limit=payload.top_k
    )

    fused = service.retriever.fuse_rrf(
        dense_candidates, sparse_candidates, k=60, top_k=payload.top_k
    )

    results = [
        CodebaseSearchResult(
            chunk_id=c.chunk_id,
            file_path=c.file_path,
            language=c.language,
            start_line=c.start_line,
            end_line=c.end_line,
            scope_path=c.scope_path,
            content=c.content,
            score=c.rrf_score or c.score,
            retrieval_mode="hybrid",
        )
        for c in fused
    ]
    return CodebaseSearchResponse(results=results, total=len(results))


@router.post(
    "/{workspace_id}/codebases/{codebase_id}/query",
    response_model=CodebaseQueryResponse,
    dependencies=[Depends(verify_csrf_token)],
)
async def query_codebase(
    workspace_id: uuid.UUID,
    codebase_id: uuid.UUID,
    payload: CodebaseQueryRequest,
    db: AsyncSession = Depends(get_db),
    membership: WorkspaceMembership = Depends(require_workspace_member),
    user: User = Depends(get_current_active_user),
    service: CodebaseService = Depends(get_codebase_service),
):
    q_record, citations = await service.query_codebase(
        db,
        workspace_id=workspace_id,
        codebase_id=codebase_id,
        query=payload.query,
        user_id=user.id,
        top_k=payload.top_k,
    )

    cit_responses = [
        CodebaseCitationResponse(
            file_path=cit.file_path,
            start_line=cit.start_line,
            end_line=cit.end_line,
            snippet_preview=cit.snippet_preview,
            citation_marker=f"[{cit.file_path}:{cit.start_line}-{cit.end_line}]",
        )
        for cit in citations
    ]

    return CodebaseQueryResponse(
        id=q_record.id,
        query=q_record.query_text,
        answer=q_record.answer_text,
        citations=cit_responses,
        retrieval_strategy=q_record.retrieval_strategy,
        latency_ms=q_record.latency_ms,
        generation_id=q_record.generation_id,
        created_at=q_record.created_at,
    )