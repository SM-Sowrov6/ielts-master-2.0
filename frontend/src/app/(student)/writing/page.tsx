import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { WritingHome } from "@/components/practice/writing";

export const metadata: Metadata = { title: "Writing" };

export default function WritingPage() {
  return (
    <SignedIn path="/writing">
      <WritingHome />
    </SignedIn>
  );
}
