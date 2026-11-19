import type { Metadata } from "next";

import { studentNav, navItem } from "@/components/layout/nav-config";
import { SignedIn } from "@/components/auth/gates";
import { ComingSoon } from "@/components/patterns/coming-soon";

const item = navItem(studentNav, "/practice");

export const metadata: Metadata = { title: item.label };

export default function Page() {
  return (
    <SignedIn path="/practice">
      <ComingSoon item={item} />
    </SignedIn>
  );
}
