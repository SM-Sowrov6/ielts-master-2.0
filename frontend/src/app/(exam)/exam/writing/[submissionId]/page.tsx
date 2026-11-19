import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { WritingExam } from "@/components/practice/writing";

export const metadata: Metadata = { title: "Writing test", robots: { index: false } };

/** Full-screen writing room (FocusShell inside WritingExam). */
export default async function WritingExamPage({
  params,
}: {
  params: Promise<{ submissionId: string }>;
}) {
  const { submissionId } = await params;
  return (
    <SignedIn path={`/exam/writing/${encodeURIComponent(submissionId)}`}>
      <WritingExam submissionId={submissionId} />
    </SignedIn>
  );
}
