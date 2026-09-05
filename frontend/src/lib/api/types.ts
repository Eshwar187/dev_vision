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