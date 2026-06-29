/** Core API utilities — auth, request, error handling. */

export const API_BASE = "/api";

let _authToken: string | null = null;

export function setAuthToken(token: string) {
  _authToken = token;
}

export function getAuthToken(): string | null {
  return _authToken;
}

export function isAuthConfigured(): boolean {
  return _authToken !== null && _authToken.length > 0;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (_authToken) {
    headers["Authorization"] = `Bearer ${_authToken}`;
  }
  return headers;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  if (res.status === 401) {
    throw new ApiError(
      "认证失败，请检查 AUTH_TOKEN 与 VITE_AUTH_TOKEN 是否一致",
      401
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail || body.message || "";
    } catch {
      // response is not JSON
    }
    const msg = detail || `请求失败 (HTTP ${res.status})`;
    throw new ApiError(msg, res.status);
  }

  return res.json();
}
