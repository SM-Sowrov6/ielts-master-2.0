/**
 * CSRF token handling for the same-origin API (docs/SECURITY_GUIDELINES.md §3).
 *
 * The backend sets a readable CSRF cookie bound to the current session; every unsafe request
 * must echo it in `X-CSRF-Token`. If the cookie is missing, a token is fetched from
 * `GET /api/v1/auth/csrf`. Tokens are never stored anywhere else (no localStorage).
 */

export const CSRF_HEADER = "X-CSRF-Token";
// `__Host-` prefixed in production (Secure), plain name in local development over http.
export const CSRF_COOKIE_NAMES = ["__Host-csrf", "ielts_csrf"] as const;
export const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCsrfCookie(
  cookieString: string = globalThis.document?.cookie ?? "",
): string | undefined {
  for (const part of cookieString.split(";")) {
    const [rawName, ...rest] = part.trim().split("=");
    if ((CSRF_COOKIE_NAMES as readonly string[]).includes(rawName ?? "")) {
      const value = decodeURIComponent(rest.join("="));
      if (value) return value;
    }
  }
  return undefined;
}

let inflight: Promise<string> | null = null;

/** Return the current CSRF token, fetching one when absent (or when `refresh` is set). */
export async function ensureCsrfToken(options: { refresh?: boolean } = {}): Promise<string> {
  if (!options.refresh) {
    const existing = readCsrfCookie();
    if (existing) return existing;
  }
  inflight ??= fetch("/api/v1/auth/csrf", { credentials: "same-origin", cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) throw new Error(`CSRF token request failed (${response.status})`);
      const body = (await response.json()) as { csrf_token: string };
      return body.csrf_token;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}
