import type { ReactNode } from "react";

import { SiteShell } from "@/components/layout/site-shell";

/** Landing page group: same public shell, full-bleed main (sections set their own width). */
export default function MarketingLayout({ children }: { children: ReactNode }) {
  return <SiteShell layout="full">{children}</SiteShell>;
}
