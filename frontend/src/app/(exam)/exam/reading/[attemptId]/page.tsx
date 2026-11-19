import type { Metadata } from "next";

import { ExamRoom } from "@/components/listening/exam-room";
import { SignedIn } from "@/components/auth/gates";
import { ExamModuleProvider } from "@/lib/exam/module";

export const metadata: Metadata = { title: "Reading test", robots: { index: false } };

/** Distraction-free exam room (FocusShell inside ExamRoom). */
export default async function ReadingExamPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return (
    <SignedIn path={`/exam/reading/${encodeURIComponent(attemptId)}`}>
      <ExamModuleProvider module="reading">
        <ExamRoom attemptId={attemptId} />
      </ExamModuleProvider>
    </SignedIn>
  );
}
