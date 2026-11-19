/**
 * Server-only environment configuration. Import only from Server Components / route handlers:
 * these values must never reach the browser bundle (no NEXT_PUBLIC_ prefix).
 */

export type ServerEnv = {
  apiInternalUrl: string;
};

export class ServerEnvError extends Error {}

export function readServerEnv(source: Record<string, string | undefined> = process.env): ServerEnv {
  const raw = source.API_INTERNAL_URL;
  if (!raw) {
    throw new ServerEnvError("API_INTERNAL_URL is not set");
  }
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new ServerEnvError("API_INTERNAL_URL is not a valid URL");
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ServerEnvError("API_INTERNAL_URL must use http or https");
  }
  return { apiInternalUrl: url.origin };
}
