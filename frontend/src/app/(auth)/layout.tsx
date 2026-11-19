import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthShell } from "@/components/auth/auth-shell";

// Account pages are never indexed.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AuthLayout({ children }: { children: ReactNode }) {
  return <AuthShell>{children}</AuthShell>;
}
