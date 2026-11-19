/** Server-only API client factory. Import only from Server Components / route handlers. */

import { createApiClient, type ApiClient } from "@/lib/api/client";
import { readServerEnv } from "@/lib/server-env";

export function serverApi(): ApiClient {
  const { apiInternalUrl } = readServerEnv();
  return createApiClient(apiInternalUrl);
}
