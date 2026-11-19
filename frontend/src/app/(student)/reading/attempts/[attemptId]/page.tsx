import type { Metadata } from "next";

import { AttemptResult } from "@/components/listening/attempt-result";
import { SignedIn } from "@/components/auth/gates";
import { ExamModuleProvider } from "@/lib/exam/module";

export const metadata: Metadata = { title: "Reading result" };

export default async function ReadingResultPage({
  params,
}: {
  params: Promise<{ attemptId: string }>;
}) {
  const { attemptId } = await params;
  return (
    <SignedIn path={`/reading/attempts/${encodeURIComponent(attemptId)}`}>
      <ExamModuleProvider module="reading">
        <AttemptResult attemptId={attemptId} />
      </ExamModuleProvider>
    </SignedIn>
  );
}
