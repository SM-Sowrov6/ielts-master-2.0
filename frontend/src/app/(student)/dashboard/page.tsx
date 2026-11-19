import { HeadphonesIcon } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { studentNav, navItem } from "@/components/layout/nav-config";
import { SignedIn } from "@/components/auth/gates";
import { ComingSoon } from "@/components/patterns/coming-soon";

const item = navItem(studentNav, "/dashboard");

export const metadata: Metadata = { title: item.label };

export default function Page() {
  return (
    <SignedIn path="/dashboard">
      <div className="space-y-8">
        <Link
          href="/listening"
          className="flex items-center gap-4 rounded-2xl border bg-card p-5 shadow-elevation-1 transition-shadow hover:shadow-elevation-2"
        >
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <HeadphonesIcon className="size-6" aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-heading text-lg font-semibold">
              Listening practice is ready
            </span>
            <span className="block text-sm text-muted-foreground">
              Take a full four-part Listening test, then review every answer.
            </span>
          </span>
          <span className="text-sm font-medium text-primary">Start →</span>
        </Link>
        <ComingSoon item={item} />
      </div>
    </SignedIn>
  );
}
