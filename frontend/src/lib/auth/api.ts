/**
 * Browser calls to the identity API (docs/API_SPECIFICATION.md §2). Session state lives only in
 * HttpOnly cookies set by the backend; nothing auth-related is stored in JavaScript storage.
 */

import { browserApi } from "@/lib/api/client";
import { ApiError, ensureOk, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Me = components["schemas"]["MeResponse"];
export type RegistrationPolicy = components["schemas"]["RegistrationPolicyResponse"];
export type RegisterInput = components["schemas"]["RegisterRequest"];

/** The signed-in user, or null when not signed in (401). Other failures throw. */
export async function fetchMe(): Promise<Me | null> {
  const result = await browserApi.GET("/api/v1/me", { cache: "no-store" });
  if (result.response.status === 401) return null;
  return unwrap(result);
}

export async function fetchRegistrationPolicy(): Promise<RegistrationPolicy> {
  return unwrap(await browserApi.GET("/api/v1/auth/registration-policy"));
}

export async function signIn(email: string, password: string): Promise<Me> {
  return unwrap(await browserApi.POST("/api/v1/auth/login", { body: { email, password } }));
}

export async function register(input: RegisterInput): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/register", { body: input }));
}

export async function verifyEmail(token: string): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/verify-email", { body: { token } }));
}

export async function resendVerification(email: string): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/verify-email/resend", { body: { email } }));
}

export async function requestPasswordReset(email: string): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/password/forgot", { body: { email } }));
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  ensureOk(
    await browserApi.POST("/api/v1/auth/password/reset", {
      body: { token, new_password: newPassword },
    }),
  );
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  ensureOk(
    await browserApi.POST("/api/v1/me/password", {
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  );
}

export async function signOut(): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/logout"));
}

export async function signOutEverywhere(): Promise<void> {
  ensureOk(await browserApi.POST("/api/v1/auth/logout-all"));
}

/** A field-level message from a 422 response, keyed by request field name. */
export function fieldErrorsFrom(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.fieldErrors) return {};
  const result: Record<string, string> = {};
  for (const item of error.fieldErrors) {
    const field = item.loc[item.loc.length - 1];
    if (typeof field === "string" && !(field in result)) {
      result[field] = item.msg.replace(/^Value error, /, "");
    }
  }
  return result;
}

/** User-facing message for an auth API error (codes are stable; titles are server-written). */
export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "rate_limited":
        return "Too many attempts. Please wait a minute and try again.";
      case "rate_limiter_unavailable":
      case "internal_error":
        return "The service is temporarily unavailable. Please try again shortly.";
      case "csrf_failed":
        return "Your session changed. Refresh the page and try again.";
      default:
        return error.message;
    }
  }
  return "We couldn't reach the server. Check your connection and try again.";
}
