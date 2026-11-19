/**
 * Typed API clients generated from the backend OpenAPI schema (`schema.d.ts`).
 * Regenerate with `pnpm api:generate` after backend API changes (CI fails on drift).
 *
 * - Browser: same-origin requests (`/api/...`); Nginx routes them to FastAPI (ADR-006), and the
 *   dev server rewrites them (next.config.ts). Cookies travel automatically (same origin).
 * - Server components: call the backend directly on the internal network (API_INTERNAL_URL).
 */

import createClient, { type Client, type Middleware } from "openapi-fetch";

import { CSRF_HEADER, UNSAFE_METHODS, ensureCsrfToken } from "@/lib/api/csrf";
import type { paths } from "@/lib/api/schema";

export type ApiClient = Client<paths>;

export function createApiClient(baseUrl: string, init?: { headers?: HeadersInit }): ApiClient {
  return createClient<paths>({
    baseUrl,
    headers: init?.headers,
    credentials: "same-origin",
    // Resolve fetch per call (not once at module load), so wrappers and test doubles apply.
    fetch: (request) => globalThis.fetch(request),
  });
}

const retryCopies = new WeakMap<Request, Request>();

/**
 * Browser-only CSRF middleware: adds `X-CSRF-Token` to unsafe requests, and if the server rejects
 * the token (`csrf_failed`, e.g. after the session changed in another tab) fetches a fresh token
 * and retries the request once.
 */
export const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    if (!UNSAFE_METHODS.has(request.method)) return undefined;
    request.headers.set(CSRF_HEADER, await ensureCsrfToken());
    retryCopies.set(request, request.clone());
    return request;
  },
  async onResponse({ request, response }) {
    const copy = retryCopies.get(request);
    retryCopies.delete(request);
    if (response.status !== 403 || !copy) return undefined;
    const problem = (await response
      .clone()
      .json()
      .catch(() => null)) as { code?: string } | null;
    if (problem?.code !== "csrf_failed") return undefined;
    const retry = new Request(copy);
    retry.headers.set(CSRF_HEADER, await ensureCsrfToken({ refresh: true }));
    return fetch(retry);
  },
};

/** Client for use in Client Components (relative, same-origin, CSRF-aware). */
export const browserApi: ApiClient = createApiClient(
  // The page's own origin (same-origin; identical to a relative URL in browsers).
  typeof window === "undefined" ? "" : window.location.origin,
);
browserApi.use(csrfMiddleware);
