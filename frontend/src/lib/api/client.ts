import type {
  User,
  Workspace,
  WorkspaceDetail,
  WorkspaceMember,
  RegisterResponse,
  LoginResponse,
  LogoutResponse,
  ErrorEnvelope,
} from "./types";

export interface LiveStatus {
  status: string;
  service: string;
  timestamp: string;
}

export interface DependencyChecks {
  database: "healthy" | "unhealthy";
  pgvector: "installed" | "missing";
  redis: "healthy" | "unhealthy";
  storage: "healthy" | "unhealthy";
}

export interface ReadyStatus {
  status: "healthy" | "unhealthy";
  checks: DependencyChecks;
  timestamp: string;
}

export interface SystemInfo {
  app_name: string;
  version: string;
  environment: string;
  debug: boolean;
  api_version: string;
  timestamp: string;
}

export interface ProbeResult<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  errorCode?: string;
  latencyMs: number;
  requestId: string | null;
}

const API_BASE = "http://localhost:8000";

function getCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)devvision_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<ProbeResult<T>> {
    const start = performance.now();
    const method = (options.method || "GET").toUpperCase();

    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (options.body && typeof options.body === "string" && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    // Explicit Double-Submit CSRF Protection for state-changing requests
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      const csrfToken = getCsrfCookie();
      if (csrfToken) {
        headers["X-CSRF-Token"] = csrfToken;
      }
    }

    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        method,
        headers,
        credentials: "include", // Essential for HttpOnly session cookie transmission
      });

      const latencyMs = Math.round(performance.now() - start);
      const requestId = res.headers.get("x-request-id");

      if (!res.ok) {
        const errorEnvelope: ErrorEnvelope | null = await res.json().catch(() => null);
        const errorMessage = errorEnvelope?.error?.message || `HTTP error: ${res.status}`;
        const errorCode = errorEnvelope?.error?.code || `HTTP_${res.status}`;
        return {
          success: false,
          data: null,
          error: errorMessage,
          errorCode,
          latencyMs,
          requestId,
        };
      }

      const data: T = await res.json();
      return {
        success: true,
        data,
        error: null,
        latencyMs,
        requestId,
      };
    } catch (err: any) {
      const latencyMs = Math.round(performance.now() - start);
      return {
        success: false,
        data: null,
        error: err?.message || "Network error. Is FastAPI running on http://localhost:8000?",
        latencyMs,
        requestId: null,
      };
    }
  }

  // --- Phase 0 Health & Diagnostics ---
  async checkLive(): Promise<ProbeResult<LiveStatus>> {
    return this.request<LiveStatus>("/health/live");
  }

  async checkReady(): Promise<ProbeResult<ReadyStatus>> {
    return this.request<ReadyStatus>("/health/ready");
  }

  async getSystemInfo(): Promise<ProbeResult<SystemInfo>> {
    return this.request<SystemInfo>("/api/v1/system/info");
  }

  // --- Phase 1: Authentication Endpoints ---
  async register(
    email: string,
    password: string,
    displayName: string
  ): Promise<ProbeResult<RegisterResponse>> {
    return this.request<RegisterResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        display_name: displayName,
      }),
    });
  }

  async login(email: string, password: string): Promise<ProbeResult<LoginResponse>> {
    return this.request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  }

  async logout(): Promise<ProbeResult<LogoutResponse>> {
    return this.request<LogoutResponse>("/api/v1/auth/logout", {
      method: "POST",
    });
  }

  async getMe(): Promise<ProbeResult<LoginResponse>> {
    return this.request<LoginResponse>("/api/v1/auth/me");
  }

  // --- Phase 1: Workspace Endpoints ---
  async createWorkspace(name: string): Promise<ProbeResult<Workspace>> {
    return this.request<Workspace>("/api/v1/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  async listWorkspaces(): Promise<ProbeResult<Workspace[]>> {
    return this.request<Workspace[]>("/api/v1/workspaces");
  }

  async getWorkspace(id: string): Promise<ProbeResult<WorkspaceDetail>> {
    return this.request<WorkspaceDetail>(`/api/v1/workspaces/${id}`);
  }

  async updateWorkspace(id: string, name: string): Promise<ProbeResult<Workspace>> {
    return this.request<Workspace>(`/api/v1/workspaces/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    });
  }

  async deleteWorkspace(id: string): Promise<ProbeResult<{ status: string; message: string }>> {
    return this.request<{ status: string; message: string }>(`/api/v1/workspaces/${id}`, {
      method: "DELETE",
    });
  }

  async listMembers(workspaceId: string): Promise<ProbeResult<{ members: WorkspaceMember[] }>> {
    return this.request<{ members: WorkspaceMember[] }>(`/api/v1/workspaces/${workspaceId}/members`);
  }

  async addMember(
    workspaceId: string,
    email: string,
    role: "admin" | "member"
  ): Promise<ProbeResult<{ status: string; message: string }>> {
    return this.request<{ status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/members`,
      {
        method: "POST",
        body: JSON.stringify({ email, role }),
      }
    );
  }

  async updateMemberRole(
    workspaceId: string,
    userId: string,
    role: "admin" | "member"
  ): Promise<ProbeResult<{ status: string; message: string }>> {
    return this.request<{ status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/members/${userId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }
    );
  }

  async removeMember(
    workspaceId: string,
    userId: string
  ): Promise<ProbeResult<{ status: string; message: string }>> {
    return this.request<{ status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/members/${userId}`,
      {
        method: "DELETE",
      }
    );
  }

  async transferOwnership(
    workspaceId: string,
    newOwnerUserId: string
  ): Promise<ProbeResult<{ status: string; message: string }>> {
    return this.request<{ status: string; message: string }>(
      `/api/v1/workspaces/${workspaceId}/transfer-ownership`,
      {
        method: "POST",
        body: JSON.stringify({ new_owner_user_id: newOwnerUserId }),
      }
    );
  }
}

export const api = new ApiClient();