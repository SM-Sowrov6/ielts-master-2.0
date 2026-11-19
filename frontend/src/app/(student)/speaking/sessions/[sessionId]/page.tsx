import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { SpeakingSessionView } from "@/components/practice/speaking";

export const metadata: Metadata = { title: "Speaking session", robots: { index: false } };

export default async function SpeakingSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return (
    <SignedIn path={`/speaking/sessions/${encodeURIComponent(sessionId)}`}>
      <SpeakingSessionView sessionId={sessionId} />
    </SignedIn>
  );
}
