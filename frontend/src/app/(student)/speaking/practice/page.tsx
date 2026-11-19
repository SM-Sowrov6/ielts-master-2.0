import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { SpeakingHome } from "@/components/practice/speaking";

export const metadata: Metadata = { title: "Speaking practice by question" };

export default function SpeakingPracticePage() {
  return (
    <SignedIn path="/speaking/practice">
      <SpeakingHome />
    </SignedIn>
  );
}
