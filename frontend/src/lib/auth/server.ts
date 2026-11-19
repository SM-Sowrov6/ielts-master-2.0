/**
 * Server-side session checks (data-access-layer pattern, Next.js authentication guide).
 * Import only from Server Components. The session cookie is forwarded to the backend on the
 * internal network; the backend is the only authority on who is signed in and what they may do.
 * `proxy.ts` performs only an optimistic cookie-presence redirect before these checks run.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { createApiClient } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { Me } from "@/lib/auth/api";
import { signInUrl } from "@/lib/auth/redirect";
import { readServerEnv } from "@/lib/server-env";

async function backendWithCookies() {
  const cookieHeader = (await cookies()).toString();
  return {
    cookieHeader,
    api: createApiClient(readServerEnv().apiInternalUrl, {
      headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    }),
  };
}

/** The signed-in user for this request, or null. Deduplicated per request. */
export const getServerUser = cache(async (): Promise<Me | null> => {
  const { cookieHeader, api } = await backendWithCookies();
  if (!cookieHeader) return null;
  const result = await api.GET("/api/v1/me", { cache: "no-store" });
  if (result.response.status === 401) return null;
  return unwrap(result);
});

/** Redirect to sign-in (returning to `path` afterwards) unless signed in. */
export async function requireUser(path: string): Promise<Me> {
  const user = await getServerUser();
  if (!user) redirect(signInUrl(path));
  return user;
}

export type StaffAccess =
  | { status: "allowed"; user: Me }
  | { status: "denied"; reason: "not_staff" | "mfa_required" }
  | { status: "signed_out" };

/**
 * Staff gate for the admin area, verified by the backend on every request (`admin.access`, and
 * staff two-factor where required). Deduplicated per request, so the admin layout and the page
 * share one backend call.
 */
export const getStaffAccess = cache(async (): Promise<StaffAccess> => {
  const { cookieHeader, api } = await backendWithCookies();
  if (!cookieHeader) return { status: "signed_out" };
  const result = await api.GET("/api/v1/admin/session", { cache: "no-store" });
  if (result.response.status === 401) return { status: "signed_out" };
  if (result.response.status === 403) {
    const code = (result.error as { code?: string } | undefined)?.code;
    return { status: "denied", reason: code === "mfa_required" ? "mfa_required" : "not_staff" };
  }
  return { status: "allowed", user: unwrap(result) };
});

/**
 * Staff gate for one admin page: redirects to sign-in (returning to `path`) when not signed in;
 * returns null when signed in but not allowed.
 */
export async function requireStaff(path: string): Promise<Me | null> {
  const access = await getStaffAccess();
  if (access.status === "signed_out") redirect(signInUrl(path));
  return access.status === "allowed" ? access.user : null;
}
