import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";

const MAX_RETRIES = 2;

/** Never retry 4xx (cannot succeed); retry network/5xx errors a couple of times. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.isClientError) return false;
  return failureCount < MAX_RETRIES;
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: shouldRetry,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false, // mutations are not idempotent unless the API says so (Idempotency-Key)
      },
    },
  });
}
