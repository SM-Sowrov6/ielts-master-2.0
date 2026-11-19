import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { SpeakingTest } from "@/components/practice/speaking";

export const metadata: Metadata = { title: "Speaking test" };

export default async function SpeakingTestPage({
  params,
}: {
  params: Promise<{ testId: string }>;
}) {
  const { testId } = await params;
  return (
    <SignedIn path={`/speaking/tests/${encodeURIComponent(testId)}`}>
      <SpeakingTest testId={testId} />
    </SignedIn>
  );
}
