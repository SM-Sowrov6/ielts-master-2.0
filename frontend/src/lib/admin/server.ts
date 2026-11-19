/**
 * Server-side reads for the admin console (Server Components only). The session cookie is
 * forwarded to the backend, which authorises each call; a widget whose permission the
 * administrator lacks receives `forbidden` and says so instead of showing data.
 */

import { cookies } from "next/headers";

import { createApiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { serverApi } from "@/lib/api/server";
import { readServerEnv } from "@/lib/server-env";

export type UsersOverview = components["schemas"]["UsersOverviewResponse"];
export type ContentOverview = components["schemas"]["ContentOverviewResponse"];
export type AuditLogPage = components["schemas"]["AuditLogPage"];

export type AdminRead<T> =
  { status: "ok"; data: T } | { status: "forbidden" } | { status: "unavailable" };

async function adminApi() {
  const cookieHeader = (await cookies()).toString();
  return createApiClient(readServerEnv().apiInternalUrl, {
    headers: cookieHeader ? { cookie: cookieHeader } : undefined,
  });
}

function settle<T>(result: { data?: T; response: Response }): AdminRead<T> {
  if (result.response.ok && result.data !== undefined) return { status: "ok", data: result.data };
  if (result.response.status === 401 || result.response.status === 403) {
    return { status: "forbidden" };
  }
  return { status: "unavailable" };
}

async function safely<T>(read: () => Promise<AdminRead<T>>): Promise<AdminRead<T>> {
  try {
    return await read();
  } catch {
    // Never surface internal hostnames or error text to the page.
    return { status: "unavailable" };
  }
}

const OPTIONS = { cache: "no-store" } as const;

export function fetchUsersOverview(): Promise<AdminRead<UsersOverview>> {
  return safely(async () =>
    settle(await (await adminApi()).GET("/api/v1/admin/overview/users", OPTIONS)),
  );
}

export function fetchContentOverview(): Promise<AdminRead<ContentOverview>> {
  return safely(async () =>
    settle(await (await adminApi()).GET("/api/v1/admin/overview/content", OPTIONS)),
  );
}

export function fetchRecentActivity(limit = 8): Promise<AdminRead<AuditLogPage>> {
  return safely(async () =>
    settle(
      await (
        await adminApi()
      ).GET("/api/v1/admin/audit-logs", { ...OPTIONS, params: { query: { limit } } }),
    ),
  );
}

/** Service readiness for the System widget (same source as the public status page). */
export async function fetchSystemStatus(): Promise<
  { status: "ok"; overall: string; checks: Record<string, string> } | { status: "unavailable" }
> {
  try {
    const { data, error } = await serverApi().GET("/readyz", {
      signal: AbortSignal.timeout(3000),
      cache: "no-store",
    });
    const readiness = data ?? error;
    if (!readiness) return { status: "unavailable" };
    return { status: "ok", overall: readiness.status, checks: readiness.checks };
  } catch {
    return { status: "unavailable" };
  }
}
