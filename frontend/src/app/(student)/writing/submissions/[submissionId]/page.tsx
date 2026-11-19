import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { WritingSubmission } from "@/components/practice/writing";

export const metadata: Metadata = { title: "Writing response", robots: { index: false } };

export default async function WritingSubmissionPage({
  params,
}: {
  params: Promise<{ submissionId: string }>;
}) {
  const { submissionId } = await params;
  return (
    <SignedIn path={`/writing/submissions/${encodeURIComponent(submissionId)}`}>
      <WritingSubmission submissionId={submissionId} />
    </SignedIn>
  );
}
