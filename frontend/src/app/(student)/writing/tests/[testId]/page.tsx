import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { WritingTest } from "@/components/practice/writing";

export const metadata: Metadata = { title: "Writing test" };

export default async function WritingTestPage({ params }: { params: Promise<{ testId: string }> }) {
  const { testId } = await params;
  return (
    <SignedIn path={`/writing/tests/${encodeURIComponent(testId)}`}>
      <WritingTest testId={testId} />
    </SignedIn>
  );
}
