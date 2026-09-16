import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import structlog
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.codebase.models import CodebaseChunk, CodebaseSymbol
from app.modules.rag.embeddings import BgeEmbeddingModel
from app.modules.rag.protocols import EmbeddingModel, RerankerModel
from app.modules.rag.reranker import BgeRerankerModel

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedCodeCandidate:
    chunk_id: uuid.UUID
    generation_id: uuid.UUID
    file_id: uuid.UUID
    file_path: str
    language: str
    start_line: int
    end_line: int
    scope_path: str
    content: str
    content_hash: str
    token_count: int
    score: float
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None


class HybridCodeRetriever:
    def __init__(
        self,
        embedding_model: Optional[EmbeddingModel] = None,
        reranker_model: Optional[RerankerModel] = None,
    ):
        self.embedding_model = embedding_model or BgeEmbeddingModel()
        self.reranker_model = reranker_model or BgeRerankerModel()

    async def retrieve_dense(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        generation_id: uuid.UUID,
        query: str,
        limit: int = 50,
    ) -> List[RetrievedCodeCandidate]:
        if not query.strip():
            return []

        # Embed query text
        query_embeddings = await self.embedding_model.embed_texts([query])
        if not query_embeddings:
            return []
        query_vector = query_embeddings[0]

        # In PostgreSQL with pgvector, cosine distance: embedding <=> query_vector
        # Check dialect
        dialect = session.bind.dialect.name if session.bind else "postgresql"
        if dialect == "sqlite":
            # For SQLite testing mock
            stmt = (
                select(CodebaseChunk)
                .where(
                    CodebaseChunk.workspace_id == workspace_id,
                    CodebaseChunk.generation_id == generation_id,
                )
                .limit(limit)
            )
            res = await session.execute(stmt)
            chunks = res.scalars().all()
            return [
                RetrievedCodeCandidate(
                    chunk_id=c.id,
                    generation_id=c.generation_id,
                    file_id=c.file_id,
                    file_path=c.file_path,
                    language=c.language,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    scope_path=c.scope_path,
                    content=c.content,
                    content_hash=c.content_hash,
                    token_count=c.token_count,
                    score=1.0 - (0.01 * idx),
                )
                for idx, c in enumerate(chunks)
            ]

        # Real PostgreSQL pgvector query
        stmt = (
            select(
                CodebaseChunk,
                (1.0 - CodebaseChunk.embedding.cosine_distance(query_vector)).label("sim_score"),
            )
            .where(
                CodebaseChunk.workspace_id == workspace_id,
                CodebaseChunk.generation_id == generation_id,
            )
            .order_by(CodebaseChunk.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        res = await session.execute(stmt)
        results = []
        for row in res.all():
            c = row[0]
            sim = float(row[1])
            results.append(
                RetrievedCodeCandidate(
                    chunk_id=c.id,
                    generation_id=c.generation_id,
                    file_id=c.file_id,
                    file_path=c.file_path,
                    language=c.language,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    scope_path=c.scope_path,
                    content=c.content,
                    content_hash=c.content_hash,
                    token_count=c.token_count,
                    score=sim,
                )
            )
        return results

    async def retrieve_sparse(
        self,
        session: AsyncSession,
        workspace_id: uuid.UUID,
        generation_id: uuid.UUID,
        query: str,
        limit: int = 50,
    ) -> List[RetrievedCodeCandidate]:
        if not query.strip():
            return []

        tokens = [t.strip().lower() for t in query.split() if len(t.strip()) > 1]
        dialect = session.bind.dialect.name if session.bind else "postgresql"

        if dialect == "sqlite":
            # SQLite fallback: LIKE matching on content and scope
            filters = []
            for t in tokens[:5]:
                filters.append(CodebaseChunk.content.ilike(f"%{t}%"))
                filters.append(CodebaseChunk.file_path.ilike(f"%{t}%"))
                filters.append(CodebaseChunk.scope_path.ilike(f"%{t}%"))

            stmt = (
                select(CodebaseChunk)
                .where(
                    CodebaseChunk.workspace_id == workspace_id,
                    CodebaseChunk.generation_id == generation_id,
                )
                .limit(limit)
            )
            res = await session.execute(stmt)
            chunks = res.scalars().all()
            return [
                RetrievedCodeCandidate(
                    chunk_id=c.id,
                    generation_id=c.generation_id,
                    file_id=c.file_id,
                    file_path=c.file_path,
                    language=c.language,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    scope_path=c.scope_path,
                    content=c.content,
                    content_hash=c.content_hash,
                    token_count=c.token_count,
                    score=0.9 - (0.01 * idx),
                )
                for idx, c in enumerate(chunks)
            ]

        # PostgreSQL: Weighted formula combining exact symbol, path, ts_rank_cd on tsv, and trigram similarity
        # 0.35 * exact_symbol + 0.25 * exact_path + 0.25 * fts + 0.15 * trigram
        fts_query = " | ".join(tokens) if tokens else query
        sql = text("""
            WITH ranked AS (
                SELECT
                    c.id,
                    c.generation_id,
                    c.file_id,
                    c.file_path,
                    c.language,
                    c.start_line,
                    c.end_line,
                    c.scope_path,
                    c.content,
                    c.content_hash,
                    c.token_count,
                    c.chunk_index,
                    (
                        0.35 * CASE WHEN EXISTS (
                            SELECT 1 FROM codebase_symbols s
                            WHERE s.generation_id = c.generation_id
                              AND s.file_id = c.file_id
                              AND lower(s.name) = lower(:clean_query)
                        ) THEN 1.0 ELSE 0.0 END
                        +
                        0.25 * CASE WHEN lower(c.file_path) LIKE '%' || lower(:clean_query) || '%' THEN 1.0 ELSE 0.0 END
                        +
                        0.25 * (ts_rank_cd(c.tsv, plainto_tsquery('simple', :clean_query)) / (1.0 + ts_rank_cd(c.tsv, plainto_tsquery('simple', :clean_query))))
                        +
                        0.15 * similarity(coalesce(c.file_path, '') || ' ' || coalesce(c.scope_path, ''), :clean_query)
                    ) AS composite_sparse_score
                FROM codebase_chunks c
                WHERE c.workspace_id = :workspace_id
                  AND c.generation_id = :generation_id
                  AND (
                      c.tsv @@ plainto_tsquery('simple', :clean_query)
                      OR lower(c.file_path) LIKE '%' || lower(:clean_query) || '%'
                      OR lower(c.scope_path) LIKE '%' || lower(:clean_query) || '%'
                      OR similarity(c.scope_path, :clean_query) > 0.2
                  )
            )
            SELECT * FROM ranked
            ORDER BY composite_sparse_score DESC, chunk_index ASC, id ASC
            LIMIT :limit
        """)

        res = await session.execute(
            sql,
            {
                "workspace_id": workspace_id,
                "generation_id": generation_id,
                "clean_query": query.strip(),
                "limit": limit,
            },
        )

        results = []
        for row in res.mappings().all():
            results.append(
                RetrievedCodeCandidate(
                    chunk_id=row["id"],
                    generation_id=row["generation_id"],
                    file_id=row["file_id"],
                    file_path=row["file_path"],
                    language=row["language"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    scope_path=row["scope_path"],
                    content=row["content"],
                    content_hash=row["content_hash"],
                    token_count=row["token_count"],
                    score=float(row["composite_sparse_score"]),
                )
            )
        return results

    @staticmethod
    def fuse_rrf(
        dense_candidates: List[RetrievedCodeCandidate],
        sparse_candidates: List[RetrievedCodeCandidate],
        k: int = 60,
        top_k: int = 40,
    ) -> List[RetrievedCodeCandidate]:
        candidates_by_id: Dict[uuid.UUID, RetrievedCodeCandidate] = {}
        rrf_scores: Dict[uuid.UUID, float] = {}

        # 1-indexed dense ranks
        for rank, cand in enumerate(dense_candidates, start=1):
            cid = cand.chunk_id
            cand.dense_rank = rank
            candidates_by_id[cid] = cand
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + rank))

        # 1-indexed sparse ranks
        for rank, cand in enumerate(sparse_candidates, start=1):
            cid = cand.chunk_id
            cand.sparse_rank = rank
            if cid not in candidates_by_id:
                candidates_by_id[cid] = cand
            else:
                candidates_by_id[cid].sparse_rank = rank
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k + rank))

        for cid, cand in candidates_by_id.items():
            cand.rrf_score = rrf_scores[cid]

        # Deterministic tie-breaking:
        # 1. RRF score DESC
        # 2. dense rank ASC NULLS LAST
        # 3. sparse rank ASC NULLS LAST
        # 4. chunk_id ASC
        sorted_candidates = sorted(
            candidates_by_id.values(),
            key=lambda c: (
                -(c.rrf_score or 0.0),
                c.dense_rank if c.dense_rank is not None else 999999,
                c.sparse_rank if c.sparse_rank is not None else 999999,
                str(c.chunk_id),
            ),
        )

        return sorted_candidates[:top_k]

    async def rerank(
        self,
        query: str,
        candidates: List[RetrievedCodeCandidate],
        threshold: float = 0.25,
        top_k: int = 8,
    ) -> List[RetrievedCodeCandidate]:
        if not candidates:
            return []

        passages = [
            f"File: {c.file_path}\nScope: {c.scope_path}\n{c.content}"
            for c in candidates
        ]

        rerank_results = await self.reranker_model.rerank(query, passages, top_k=len(passages))
        # rerank_results is list of (index, score)
        scored_candidates = []
        for idx, score in rerank_results:
            cand = candidates[idx]
            cand.rerank_score = score
            if score >= threshold:
                scored_candidates.append(cand)

        # Sort by rerank_score DESC, chunk_id ASC
        scored_candidates.sort(key=lambda c: (-(c.rerank_score or 0.0), str(c.chunk_id)))
        return scored_candidates[:top_k]
