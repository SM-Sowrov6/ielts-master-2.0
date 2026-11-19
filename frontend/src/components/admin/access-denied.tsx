import { ShieldAlertIcon } from "lucide-react";
import Link from "next/link";

import { BrandMark } from "@/components/layout/brand";
import { EmptyState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";

const COPY = {
  not_staff: {
    title: "You don't have access to this area",
    description:
      "The admin console is available to authorised staff accounts only. If you think this is a mistake, contact an administrator.",
  },
  mfa_required: {
    title: "Two-factor authentication required",
    description:
      "Staff access in this environment requires two-factor authentication, which is not available yet. Your account has not been granted access to the admin console.",
  },
} as const;

/** Shown instead of the admin console (no admin navigation) when the backend refuses access. */
export function AdminAccessDenied({ reason }: { reason: "not_staff" | "mfa_required" }) {
  const copy = COPY[reason];
  return (
    <main
      id="main-content"
      className="mx-auto flex min-h-dvh w-full max-w-xl flex-col items-center justify-center gap-6 px-4 py-12"
    >
      <BrandMark />
      <h1 className="sr-only">Access denied</h1>
      <EmptyState
        icon={ShieldAlertIcon}
        title={copy.title}
        description={copy.description}
        className="w-full bg-background"
        action={
          <Button asChild variant="outline">
            <Link href="/dashboard">Go to your dashboard</Link>
          </Button>
        }
      />
    </main>
  );
}
