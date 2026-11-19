import type { ReactNode } from "react";

import { SiteShell } from "@/components/layout/site-shell";

/**
 * Signed-in student pages live inside the main website: same header (with the app sections in
 * the navigation), footer and styling. Each page still verifies the session on the server.
 */
export default function StudentLayout({ children }: { children: ReactNode }) {
  return <SiteShell>{children}</SiteShell>;
}
