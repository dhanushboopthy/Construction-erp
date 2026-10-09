import type { ApiErrorBody, TokenResponse } from "./types";

/**
 * Thin fetch wrapper.
 * - The access token is kept in memory only (never localStorage).
 * - The refresh token is an httpOnly cookie; on a 401 we refresh once and retry.
 * - Every failure becomes an ApiError carrying the API's {code, message, field}.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.body = body;
  }

  get requiresOwnerApproval(): boolean {
    return this.body.requires_owner_approval === true;
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponse | null> | null = null;
let onSessionEnded: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setSessionEndedHandler(handler: (() => void) | null): void {
  onSessionEnded = handler;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = { code: "HTTP_ERROR", message: response.statusText, field: null, request_id: null };
  }
  return new ApiError(response.status, body);
}

export async function refreshSession(): Promise<TokenResponse | null> {
  refreshInFlight ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then(async (response) => {
      if (!response.ok) return null;
      const data = (await response.json()) as TokenResponse;
      setAccessToken(data.access_token);
      return data;
    })
    .catch(() => null)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });

  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    const refreshed = await refreshSession();
    if (refreshed) return api<T>(path, init, false);
    setAccessToken(null);
    onSessionEnded?.();
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const json = (value: unknown): string => JSON.stringify(value);
