import createClient from "openapi-fetch";
import type { paths, Schemas } from "@twinpm/api-client";

export type { Schemas };

const CSRF_COOKIE = "twinpm_csrf";
const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

export function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`))
    ?.split("=")[1];
}

function withCsrf(req: Request): Request {
  if (SAFE.has(req.method)) return req;
  const token = readCookie(CSRF_COOKIE);
  if (!token) return req;
  const headers = new Headers(req.headers);
  headers.set("x-csrf-token", decodeURIComponent(token));
  return new Request(req, { headers });
}

let refreshing: Promise<boolean> | null = null;

/** Refresh the session once, sharing the in-flight request between concurrent callers. */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

/** fetch with CSRF header injection and a single transparent refresh on 401. */
export async function authFetch(input: Request): Promise<Response> {
  const retry = input.clone();
  const res = await fetch(withCsrf(input));
  if (res.status !== 401 || input.url.includes("/api/v1/auth/")) return res;
  if (!(await refreshSession())) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    return res;
  }
  return fetch(withCsrf(retry));
}

export const api = createClient<paths>({ baseUrl: "", credentials: "include", fetch: authFetch });

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}

interface Envelope {
  error?: { code?: string; message?: string; request_id?: string };
}

/** Unwrap an openapi-fetch result, throwing a typed ApiError on failure. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || result.data === undefined) {
    const env = (result.error ?? {}) as Envelope;
    throw new ApiError(
      result.response.status,
      env.error?.code ?? `http_${result.response.status}`,
      env.error?.message ?? "Request failed",
      env.error?.request_id,
    );
  }
  return result.data;
}
