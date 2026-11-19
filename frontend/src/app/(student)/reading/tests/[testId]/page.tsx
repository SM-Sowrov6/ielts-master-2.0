import type { Metadata } from "next";

import { TestIntro } from "@/components/listening/test-intro";
import { SignedIn } from "@/components/auth/gates";
import { ExamModuleProvider } from "@/lib/exam/module";

export const metadata: Metadata = { title: "Reading test" };

export default async function ReadingTestPage({ params }: { params: Promise<{ testId: string }> }) {
  const { testId } = await params;
  return (
    <SignedIn path={`/reading/tests/${encodeURIComponent(testId)}`}>
      <ExamModuleProvider module="reading">
        <TestIntro testId={testId} />
      </ExamModuleProvider>
    </SignedIn>
  );
}
