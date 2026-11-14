// Browser-side calls to NEXORA Core through the portal's /v1 proxy (same origin, cookies included).
// Unsafe methods carry the double-submit CSRF token (Core decision D5).

export const CSRF_COOKIE = "__Host-nexora_csrf";

export type ApiResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string; headers: Headers | null };

export function readCookie(name: string, source: string = document.cookie): string | null {
  for (const part of source.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

async function csrfToken(): Promise<string> {
  let token = readCookie(CSRF_COOKIE);
  if (!token) {
    await fetch("/v1/auth/csrf", { credentials: "same-origin" });
    token = readCookie(CSRF_COOKIE);
  }
  return token ?? "";
}

export async function api<T>(
  path: string,
  { method = "GET", json }: { method?: "GET" | "POST" | "PATCH" | "DELETE"; json?: unknown } = {},
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-Token"] = await csrfToken();
  if (json !== undefined) headers["content-type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      body: json === undefined ? undefined : JSON.stringify(json),
    });
  } catch {
    return { ok: false, status: 0, error: "network", headers: null };
  }
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (res.ok) return { ok: true, status: res.status, data: body as T };
  const error =
    body && typeof body === "object" && "error" in body && typeof body.error === "string"
      ? body.error
      : res.status === 422
        ? "invalid_input"
        : "unexpected";
  return { ok: false, status: res.status, error, headers: res.headers };
}
