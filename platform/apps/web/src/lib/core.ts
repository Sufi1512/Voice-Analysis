// Server-side access to NEXORA Core. Forwards the visitor's cookies, never caches across requests.
import { cookies } from "next/headers";
import { cache } from "react";
import type { Me, MyOrganization, Organization } from "./types";

const CORE = process.env.NEXORA_API_URL ?? "http://localhost:8080";

export class CoreError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
  ) {
    super(`NEXORA Core answered ${status}${code ? ` (${code})` : ""}`);
  }
}

export async function core<T>(path: string): Promise<T> {
  const jar = await cookies();
  const res = await fetch(`${CORE}${path}`, {
    headers: { cookie: jar.toString(), accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: unknown } | null;
    throw new CoreError(res.status, typeof body?.error === "string" ? body.error : null);
  }
  return (await res.json()) as T;
}

/** The signed-in person, or null. Deduplicated per request (layout and page share it). */
export const getMe = cache(async (): Promise<Me | null> => {
  try {
    return await core<Me>("/v1/me");
  } catch (error) {
    if (error instanceof CoreError && error.status === 401) return null;
    throw error;
  }
});

/** The person's organizations; empty when signed out (layouts redirect on getMe() instead). */
export const getMyOrganizations = cache(async (): Promise<MyOrganization[]> => {
  try {
    return (await core<{ items: MyOrganization[] }>("/v1/organizations")).items;
  } catch (error) {
    if (error instanceof CoreError && error.status === 401) return [];
    throw error;
  }
});

/** One organization, or null when the person may not see it (Core answers 404 either way). */
export const getOrganization = cache(async (org: string): Promise<Organization | null> => {
  try {
    return await core<Organization>(`/v1/organizations/${encodeURIComponent(org)}`);
  } catch (error) {
    if (error instanceof CoreError && error.status === 404) return null;
    throw error;
  }
});

export type Readiness = { reachable: boolean; database: "up" | "down" | "unknown"; checkedAt: string };

export async function getReadiness(): Promise<Readiness> {
  const checkedAt = new Date().toISOString();
  try {
    const res = await fetch(`${CORE}/readyz`, { cache: "no-store", signal: AbortSignal.timeout(3000) });
    const body = (await res.json()) as { checks?: { database?: "up" | "down" } };
    return { reachable: true, database: body.checks?.database ?? "unknown", checkedAt };
  } catch {
    return { reachable: false, database: "unknown", checkedAt };
  }
}
