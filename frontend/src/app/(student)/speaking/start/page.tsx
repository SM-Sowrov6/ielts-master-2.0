import type { Metadata } from "next";
import { Suspense } from "react";

import { SignedIn } from "@/components/auth/gates";
import { LoadingState } from "@/components/patterns/states";
import { StartSpeaking } from "@/components/speaking-room/landing";

export const metadata: Metadata = { title: "Start Speaking practice" };

export default function StartSpeakingPage() {
  return (
    <SignedIn path="/speaking/start">
      <Suspense fallback={<LoadingState label="Preparing…" />}>
        <StartSpeaking />
      </Suspense>
    </SignedIn>
  );
}
