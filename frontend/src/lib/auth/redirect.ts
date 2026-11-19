/**
 * Post-sign-in destination from `?next=`. Only same-site relative paths are accepted, so the
 * parameter cannot be used as an open redirect (e.g. `//evil.example`, `/\evil`, `https://...`).
 */
export const DEFAULT_AFTER_SIGN_IN = "/dashboard";

export function safeNext(next: string | null | undefined): string {
  if (!next || next.length > 512) return DEFAULT_AFTER_SIGN_IN;
  if (!next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return DEFAULT_AFTER_SIGN_IN;
  }
  if (/[\u0000-\u001f\\]/.test(next)) return DEFAULT_AFTER_SIGN_IN;
  try {
    const url = new URL(next, "https://placeholder.invalid");
    if (url.origin !== "https://placeholder.invalid") return DEFAULT_AFTER_SIGN_IN;
    const path = `${url.pathname}${url.search}${url.hash}`;
    // Never bounce back into the auth pages themselves.
    if (/^\/(sign-in|register|forgot-password|reset-password|verify-email)(\/|$|\?)/.test(path)) {
      return DEFAULT_AFTER_SIGN_IN;
    }
    return path;
  } catch {
    return DEFAULT_AFTER_SIGN_IN;
  }
}

export function signInUrl(next: string): string {
  return `/sign-in?next=${encodeURIComponent(next)}`;
}

/** Where students land after signing in: the main website (its header shows the app sections). */
export const STUDENT_HOME = "/";

/** The home of the Super Admin console. */
export const ADMIN_HOME = "/admin";

function isAdminPath(path: string): boolean {
  return (
    path === ADMIN_HOME || path.startsWith(`${ADMIN_HOME}/`) || path.startsWith(`${ADMIN_HOME}?`)
  );
}

/**
 * Where to go after signing in (or when an already signed-in user opens the sign-in page).
 * A UI routing convenience only: the admin area re-verifies staff access on the server for every
 * page and API call, so editing this logic or the user object in the browser grants nothing.
 *
 * - An explicit, safe `next` wins, except that non-staff accounts are never sent into /admin.
 * - Otherwise staff land on the admin console and students on the main website (home).
 */
export function destinationAfterSignIn(
  user: { permissions: readonly string[] },
  next: string | null | undefined,
): string {
  const staff = user.permissions.includes("admin.access");
  const fallback = staff ? ADMIN_HOME : STUDENT_HOME;
  if (!next) return fallback;
  const target = safeNext(next);
  // safeNext answers the default for unsafe input: treat that as "no preference".
  if (target === DEFAULT_AFTER_SIGN_IN && next !== DEFAULT_AFTER_SIGN_IN) return fallback;
  if (isAdminPath(target) && !staff) return STUDENT_HOME;
  return target;
}
