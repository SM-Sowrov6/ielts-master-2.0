import { ShieldAlertIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { requireStaff, requireUser } from "@/lib/auth/server";

/**
 * Page-level guards (Server Components). Checks run in each page rather than in layouts,
 * because layouts are not re-rendered on client navigation between their child routes.
 */
export async function SignedIn({ path, children }: { path: string; children: ReactNode }) {
  await requireUser(path);
  return <>{children}</>;
}

export async function StaffOnly({ path, children }: { path: string; children: ReactNode }) {
  const staff = await requireStaff(path);
  if (!staff) {
    return (
      <EmptyState
        icon={ShieldAlertIcon}
        title="You don't have access to this area"
        description="The admin area is available to staff accounts only. If you think this is a mistake, contact an administrator."
        action={
          <Button asChild variant="outline">
            <Link href="/dashboard">Go to your dashboard</Link>
          </Button>
        }
      />
    );
  }
  return <>{children}</>;
}
