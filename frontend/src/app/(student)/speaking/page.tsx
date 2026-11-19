import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { SpeakingLanding } from "@/components/speaking-room/landing";

export const metadata: Metadata = { title: "Speaking" };

export default function SpeakingPage() {
  return (
    <SignedIn path="/speaking">
      <SpeakingLanding />
    </SignedIn>
  );
}
