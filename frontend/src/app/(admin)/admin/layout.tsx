import type { Metadata } from "next";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AdminAccessDenied } from "@/components/admin/access-denied";
import { AdminShell } from "@/components/admin/admin-shell";
import { getStaffAccess } from "@/lib/auth/server";
import { signInUrl } from "@/lib/auth/redirect";

// Admin pages are never indexed.
export const metadata: Metadata = { robots: { index: false, follow: false } };

/**
 * Super Admin console layout. The staff session is verified by the backend before any admin
 * chrome is rendered, so non-staff accounts never see the console's structure. Every page also
 * re-checks access itself (<StaffOnly>), because layouts are not re-rendered on client navigation,
 * and every admin API call is authorised by the backend independently.
 */
export default async function AdminLayout({ children }: { children: ReactNode }) {
  const access = await getStaffAccess();
  if (access.status === "signed_out") redirect(signInUrl("/admin"));
  if (access.status === "denied") return <AdminAccessDenied reason={access.reason} />;
  return <AdminShell user={access.user}>{children}</AdminShell>;
}
