/**
 * Session-scoped conversation storage (sessionStorage: this tab only, cleared when it closes).
 * Keyed by the signed-in user's id (or "guest"), so signing out or switching accounts never
 * shows another person's conversation. Nothing is stored on the server.
 */

import type { ChatMessage } from "@/lib/assistant/api";

const PREFIX = "ielts-assistant:";
const MAX_STORED = 40;

function key(owner: string): string {
  return `${PREFIX}${owner}`;
}

function isMessage(value: unknown): value is ChatMessage {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (v.role === "user" || v.role === "assistant") && typeof v.content === "string";
}

export function loadConversation(owner: string): ChatMessage[] {
  try {
    const raw = globalThis.sessionStorage?.getItem(key(owner));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isMessage).slice(-MAX_STORED) : [];
  } catch {
    return [];
  }
}

export function saveConversation(owner: string, messages: ChatMessage[]): void {
  try {
    const store = globalThis.sessionStorage;
    if (!store) return;
    // Only one conversation is kept per tab: drop other owners' (e.g. after sign-out).
    for (let i = store.length - 1; i >= 0; i--) {
      const k = store.key(i);
      if (k?.startsWith(PREFIX) && k !== key(owner)) store.removeItem(k);
    }
    if (messages.length === 0) store.removeItem(key(owner));
    else store.setItem(key(owner), JSON.stringify(messages.slice(-MAX_STORED)));
  } catch {
    // Storage unavailable (private mode, quota): the conversation simply isn't kept.
  }
}
