import type { Metadata } from "next";

import { AttemptHistory } from "@/components/listening/attempt-history";
import { SignedIn } from "@/components/auth/gates";
import { ExamModuleProvider } from "@/lib/exam/module";

export const metadata: Metadata = { title: "Reading attempts" };

export default function ReadingHistoryPage() {
  return (
    <SignedIn path="/reading/history">
      <ExamModuleProvider module="reading">
        <AttemptHistory />
      </ExamModuleProvider>
    </SignedIn>
  );
}
