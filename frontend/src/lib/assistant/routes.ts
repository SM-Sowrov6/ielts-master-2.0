/**
 * Where the assistant may appear and which links it may render.
 *
 * Hidden during focused, timed or recorded activities so it never interferes: exam rooms
 * (Listening, Reading, Writing editor), Speaking sessions and live rooms, plus the staff console.
 */

const HIDDEN_PREFIXES = [
  "/exam",
  "/speaking-room",
  "/speaking/rooms",
  "/speaking/sessions",
  "/speaking/start",
  "/admin",
] as const;

export function assistantHiddenOn(pathname: string): boolean {
  return HIDDEN_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Only same-site paths are rendered as links; anything else is shown as plain text. */
export function safeInternalHref(href: string): string | null {
  if (!/^\/(?!\/)[\w\-./?=&#%]*$/.test(href)) return null;
  return href;
}
