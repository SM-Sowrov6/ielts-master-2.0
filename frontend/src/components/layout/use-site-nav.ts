"use client";

import { memberNav, publicNav, type PublicNavItem } from "@/components/layout/nav-config";
import { useCurrentUser } from "@/lib/auth/hooks";

/**
 * Header items for the current visitor: landing-page sections when signed out, the app sections
 * when signed in. Display only; every page and API still checks the session on the server.
 */
export function useSiteNav(): readonly PublicNavItem[] {
  const { data: user } = useCurrentUser();
  return user ? memberNav : publicNav;
}
