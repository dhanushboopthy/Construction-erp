import type { ApiErrorBody, TokenResponse } from "./types";

/**
 * Thin fetch wrapper.
 * - The access token is kept in memory only (never localStorage).
 * - The refresh token is an httpOnly cookie; on a 401 we refresh once and retry.
 * - Every failure becomes an ApiError carrying the API's {code, message, field}.
 *
 * `createClient` makes one such client per sign-in: the company app's below, and the Duolink
 * admin's (src/admin/client.ts), which has its own token and refresh path.
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

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = { code: "HTTP_ERROR", message: response.statusText, field: null, request_id: null };
  }
  return new ApiError(response.status, body);
}

export interface ApiClient<Session extends { access_token: string }> {
  setAccessToken: (token: string | null) => void;
  setSessionEndedHandler: (handler: (() => void) | null) => void;
  refreshSession: () => Promise<Session | null>;
  api: <T>(path: string, init?: RequestInit, retry?: boolean) => Promise<T>;
  /** The fetch for files: with the access token, failures as ApiError. */
  fetchFile: (path: string) => Promise<Blob>;
}

/** `base` is prefixed to every path; `authPrefix` marks the sign-in routes, which are never
 * retried after a refresh. */
export function createClient<Session extends { access_token: string }>({
  base,
  authPrefix,
}: {
  base: string;
  authPrefix: string;
}): ApiClient<Session> {
  let accessToken: string | null = null;
  let refreshInFlight: Promise<Session | null> | null = null;
  let onSessionEnded: (() => void) | null = null;

  function refreshSession(): Promise<Session | null> {
    refreshInFlight ??= fetch(`${base}${authPrefix}refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const data = (await response.json()) as Session;
        accessToken = data.access_token;
        return data;
      })
      .catch(() => null)
      .finally(() => {
        refreshInFlight = null;
      });
    return refreshInFlight;
  }

  async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(init.headers);
    // A FormData body (file upload) sets its own multipart Content-Type with the boundary.
    if (
      init.body !== undefined &&
      !(init.body instanceof FormData) &&
      !headers.has("Content-Type")
    ) {
      headers.set("Content-Type", "application/json");
    }
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

    const response = await fetch(`${base}${path}`, { ...init, headers, credentials: "include" });

    if (response.status === 401 && retry && !path.startsWith(authPrefix)) {
      const refreshed = await refreshSession();
      if (refreshed) return api<T>(path, init, false);
      accessToken = null;
      onSessionEnded?.();
    }
    if (!response.ok) throw await parseError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async function fetchFile(path: string): Promise<Blob> {
    const headers = new Headers();
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    const response = await fetch(`${base}${path}`, { headers, credentials: "include" });
    if (!response.ok) throw await parseError(response);
    return response.blob();
  }

  return {
    setAccessToken: (token) => {
      accessToken = token;
    },
    setSessionEndedHandler: (handler) => {
      onSessionEnded = handler;
    },
    refreshSession,
    api,
    fetchFile,
  };
}

/** The company app's client: /api/v1, signed in at /api/v1/auth. */
const company = createClient<TokenResponse>({ base: "/api/v1", authPrefix: "/auth/" });

export const { setAccessToken, setSessionEndedHandler, refreshSession, api } = company;

export const json = (value: unknown): string => JSON.stringify(value);

/** Open a PDF in a new tab. The request carries the access token, so a plain link cannot do it. */
export async function openFile(path: string): Promise<void> {
  const url = URL.createObjectURL(await company.fetchFile(path));
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Download a file (spreadsheet, PDF) with the access token and hand it to the browser. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = URL.createObjectURL(await company.fetchFile(path));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
