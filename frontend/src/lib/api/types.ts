export interface User {
  id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  created_by: string | null;
  role: "owner" | "admin" | "member";
  created_at: string;
}

export interface WorkspaceDetail extends Workspace {
  member_count: number;
}

export interface WorkspaceMember {
  user_id: string;
  email: string;
  display_name: string;
  role: "owner" | "admin" | "member";
  joined_at: string;
}

export interface RegisterResponse {
  status: string;
  message: string;
  user: User | null;
  workspace: {
    id: string;
    name: string;
    slug: string;
    role: string;
  } | null;
}

export interface LoginResponse {
  user: User;
}

export interface LogoutResponse {
  status: string;
  message: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details: Record<string, any>;
    request_id: string;
  };
}

// --- Phase 2: Document Management Types ---
export interface DocumentItem {
  id: string;
  workspace_id: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  checksum: string;
  status: "uploaded" | "processing" | "ready" | "failed";
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  next_cursor: string | null;
}

export interface DocumentDeleteResponse {
  status: string;
  message: string;
}

// --- Phase 3: RAG Pipeline Types ---
export interface RagCitation {
  citation_marker: number;
  document_id: string | null;
  chunk_id: string | null;
  document_name: string;
  page_number: number | null;
  section_heading: string | null;
  excerpt: string;
  rank: number;
  score: number;
}

export interface RagQueryResponse {
  query_id: string;
  query_text: string;
  answer: string;
  has_unverified_claims: boolean;
  processing_time_ms: number;
  citations: RagCitation[];
  created_at: string;
}

export interface RagHistoryItem {
  id: string;
  workspace_id: string;
  user_id: string | null;
  query_text: string;
  answer: string;
  has_unverified_claims: boolean;
  retrieval_chunks_count: number;
  processing_time_ms: number;
  created_at: string;
  citations: RagCitation[];
}

export interface RagHistoryResponse {
  items: RagHistoryItem[];
  total: number;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  section_heading: string | null;
  token_count: number;
  generation_id: string;
  created_at: string;
}

export interface DocumentChunksResponse {
  document_id: string;
  active_generation_id: string | null;
  total_chunks: number;
  chunks: DocumentChunk[];
}

export interface ReindexResponse {
  document_id: string;
  generation_id: string | null;
  status: string;
  message: string;
}

// --- Phase 7: Codebase Intelligence & Code RAG Types ---
export interface CodebaseItem {
  id: string;
  workspace_id: string;
  name: string;
  repository_url: string | null;
  default_branch: string;
  active_generation_id: string | null;
  is_indexed: boolean;
  created_at: string;
  updated_at: string;
}

export interface CodebaseCreateRequest {
  name: string;
  repository_url?: string;
  default_branch?: string;
}

export interface CodebaseListResponse {
  items: CodebaseItem[];
  total: number;
}

export interface CodebaseGenerationResponse {
  id: string;
  codebase_id: string;
  workspace_id: string;
  generation_number: number;
  status: "building" | "active" | "retired" | "failed";
  pipeline_version: string;
  embedding_model_revision: string;
  commit_hash: string | null;
  branch: string | null;
  total_files: number;
  total_symbols: number;
  total_chunks: number;
  error_message: string | null;
  activated_at: string | null;
  retired_at: string | null;
  created_at: string;
}

export interface CodebaseFileItem {
  id: string;
  generation_id: string;
  codebase_id: string;
  file_path: string;
  language: string;
  content_hash: string;
  byte_size: number;
  line_count: number;
  created_at: string;
}

export interface CodebaseFileListResponse {
  items: CodebaseFileItem[];
  total: number;
  next_cursor: string | null;
}

export interface CodebaseSymbolItem {
  id: string;
  generation_id: string;
  file_id: string;
  name: string;
  symbol_type: string;
  parent_symbol_id: string | null;
  start_line: number;
  end_line: number;
  signature: string | null;
  docstring: string | null;
}

export interface CodebaseSymbolListResponse {
  items: CodebaseSymbolItem[];
  total: number;
  next_cursor: string | null;
}

export interface CodebaseSearchResultItem {
  chunk_id: string;
  file_path: string;
  language: string;
  start_line: number;
  end_line: number;
  scope_path: string;
  content: string;
  score: number;
  retrieval_mode: string;
}

export interface CodebaseSearchResponse {
  results: CodebaseSearchResultItem[];
  total: number;
}

export interface CodebaseCitationItem {
  file_path: string;
  start_line: number;
  end_line: number;
  snippet_preview: string;
  citation_marker: string;
}

export interface CodebaseQueryResponse {
  id: string;
  query: string;
  answer: string;
  citations: CodebaseCitationItem[];
  retrieval_strategy: string;
  latency_ms: number;
  generation_id: string;
  created_at: string;
}