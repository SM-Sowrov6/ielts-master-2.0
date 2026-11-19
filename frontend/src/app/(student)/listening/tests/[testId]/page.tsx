import type { Metadata } from "next";

import { TestIntro } from "@/components/listening/test-intro";
import { SignedIn } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Listening test" };

export default async function ListeningTestPage({
  params,
}: {
  params: Promise<{ testId: string }>;
}) {
  const { testId } = await params;
  return (
    <SignedIn path={`/listening/tests/${encodeURIComponent(testId)}`}>
      <TestIntro testId={testId} />
    </SignedIn>
  );
}
