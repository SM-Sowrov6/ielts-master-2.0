import type { Metadata } from "next";

import { AttemptResult } from "@/components/listening/attempt-result";
import { SignedIn } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Listening result" };

export default async function ListeningResultPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return (
    <SignedIn path={`/listening/attempts/${encodeURIComponent(attemptId)}`}>
      <AttemptResult attemptId={attemptId} />
    </SignedIn>
  );
}
