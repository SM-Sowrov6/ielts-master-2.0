/**
 * Site assistant API (/api/v1/assistant). Same-origin and CSRF-aware through `browserApi`;
 * the provider key never reaches the browser. Only the conversation and the current path are
 * sent; the server turns the path into a curated page description.
 */

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type ChatMessage = components["schemas"]["MessageIn"];

/** Most recent messages sent with each request (the server keeps fewer for the model). */
export const MAX_SENT_MESSAGES = 16;
export const MAX_MESSAGE_CHARS = 2000;

export async function fetchAssistantStatus(): Promise<boolean> {
  const out = unwrap(await browserApi.GET("/api/v1/assistant/status", { cache: "no-store" }));
  return out.available;
}

export async function sendAssistantMessage(
  messages: ChatMessage[],
  path: string,
  signal?: AbortSignal,
): Promise<string> {
  const out = unwrap(
    await browserApi.POST("/api/v1/assistant/chat", {
      body: { messages: messages.slice(-MAX_SENT_MESSAGES), page: { path } },
      signal,
    }),
  );
  return out.content;
}
