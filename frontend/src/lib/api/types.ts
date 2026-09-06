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