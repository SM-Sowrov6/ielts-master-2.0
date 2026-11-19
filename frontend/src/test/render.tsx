import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import type { Me } from "@/lib/auth/api";

export const SAMPLE_USER: Me = {
  id: "0190f0c2-7d1c-7a00-8000-000000000001",
  email: "amina@example.test",
  full_name: "Amina Rahman",
  email_verified: true,
  roles: ["student"],
  permissions: [],
};

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

/**
 * Render with the app's client providers. `fetch` is stubbed: GET /api/v1/me answers as the given
 * user (or 401 when signed out); `routes` can answer other requests. Returns the fetch mock.
 */
export function renderWithProviders(
  ui: ReactElement,
  {
    me = null,
    routes = {},
  }: {
    me?: Me | null;
    /** Handlers get the RequestInit (when given) and the Request itself (openapi-fetch). */
    routes?: Record<
      string,
      (init?: RequestInit, request?: Request) => Response | Promise<Response>
    >;
  } = {},
): RenderResult & { fetchMock: ReturnType<typeof vi.fn> } {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request =
      input instanceof Request
        ? input
        : new Request(new URL(String(input), "http://localhost"), init);
    const path = new URL(request.url, "http://localhost").pathname;
    const handler = routes[`${request.method} ${path}`];
    if (handler) return handler(init, request);
    if (path === "/api/v1/me") {
      return me
        ? json(200, me)
        : json(401, { code: "not_authenticated", title: "Sign in to continue." });
    }
    if (path === "/api/v1/auth/csrf") return json(200, { csrf_token: "test-csrf-token" });
    return json(404, { code: "not_found", title: "Not found" });
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { ...result, fetchMock };
}
