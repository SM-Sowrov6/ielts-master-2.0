import { NextResponse, type NextRequest } from "next/server";

/**
 * Optimistic route protection (Next.js authentication guide): redirect to sign-in when a
 * protected page is requested WITHOUT a session cookie. It never decides access on its own:
 * every protected page re-verifies the session with the backend (components/auth/gates.tsx),
 * and the backend authorises every API call. Public previews (/exam/preview,
 * /speaking-room/preview) and the public library are not listed here.
 */
const PROTECTED_PREFIXES = [
  "/dashboard",
  "/practice",
  "/mock-tests",
  "/writing",
  "/speaking",
  "/progress",
  "/coach",
  "/account",
  "/admin",
  "/listening",
  "/exam/listening",
  "/reading",
  "/exam/reading",
  "/exam/writing",
];
const SESSION_COOKIES = ["__Host-session", "ielts_session"];

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (isProtectedPath(pathname) && !SESSION_COOKIES.some((n) => request.cookies.has(n))) {
    const url = new URL("/sign-in", request.url);
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api/|_next/|healthz|favicon.ico).*)"],
};
