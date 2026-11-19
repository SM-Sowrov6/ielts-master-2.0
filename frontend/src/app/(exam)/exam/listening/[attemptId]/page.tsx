import type { Metadata } from "next";

import { ExamRoom } from "@/components/listening/exam-room";
import { SignedIn } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Listening test", robots: { index: false } };

/** Distraction-free exam room (FocusShell inside ExamRoom). */
export default async function ListeningExamPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return (
    <SignedIn path={`/exam/listening/${encodeURIComponent(attemptId)}`}>
      <ExamRoom attemptId={attemptId} />
    </SignedIn>
  );
}
