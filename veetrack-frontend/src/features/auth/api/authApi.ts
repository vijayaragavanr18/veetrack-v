/**
 * Auth API client — all calls to /api/v1/auth/*.
 *
 * Refresh tokens are stored in an httpOnly cookie by the server (path /api/v1/auth).
 * The access token lives only in the Zustand auth store (in-memory, not localStorage).
 *
 * apiFetch() is a thin wrapper that retries once with a token refresh on 401.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface AuthUser {
  id: string;
  email: string;
  role: string;
  workspace_id: string;
}

export interface TokenPair {
  access_token: string;
  token_type: "bearer";
}

export interface LoginRequest {
  email: string;
  password: string;
  workspace_id: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  workspace_name: string;
}

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function _request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include", // send httpOnly cookie for refresh
    headers: {
      "Content-Type": "application/json",
      "Bypass-Tunnel-Reminder": "true",
      "ngrok-skip-browser-warning": "true",
      ...init.headers,
    },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (body.detail) {
        if (typeof body.detail === "string") {
          message = body.detail;
        } else if (Array.isArray(body.detail)) {
          message = body.detail.map((err: unknown) => {
            if (typeof err === "object" && err !== null && "msg" in err) {
              return (err as { msg: string }).msg;
            }
            return JSON.stringify(err);
          }).join(", ");
        } else {
          message = JSON.stringify(body.detail);
        }
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth endpoints
// ---------------------------------------------------------------------------

export async function apiRegister(req: RegisterRequest): Promise<TokenPair> {
  return _request<TokenPair>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function apiLogin(req: LoginRequest): Promise<TokenPair> {
  return _request<TokenPair>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function apiRefresh(): Promise<TokenPair> {
  return _request<TokenPair>("/api/v1/auth/refresh", { method: "POST" });
}

export async function apiLogout(): Promise<void> {
  return _request<void>("/api/v1/auth/logout", { method: "POST" });
}

export async function apiMe(accessToken: string): Promise<AuthUser> {
  return _request<AuthUser>("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// ---------------------------------------------------------------------------
// Authenticated fetch with automatic token refresh on 401
// ---------------------------------------------------------------------------

/**
 * Fetch a protected endpoint with the current access token.
 * On 401, attempts one silent token refresh then retries.
 * Throws ApiError if refresh also fails.
 */
export async function apiFetch<T>(
  path: string,
  accessToken: string,
  init: RequestInit = {},
  onTokenRefreshed?: (newToken: string) => void,
): Promise<T> {
  try {
    return await _request<T>(path, {
      ...init,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...init.headers,
      },
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      const refreshed = await apiRefresh();
      onTokenRefreshed?.(refreshed.access_token);
      return _request<T>(path, {
        ...init,
        headers: {
          Authorization: `Bearer ${refreshed.access_token}`,
          ...init.headers,
        },
      });
    }
    throw err;
  }
}

export { ApiError };
