import type { Metadata } from "next";

import { ListeningHome as ReadingHome } from "@/components/listening/listening-home";
import { SignedIn } from "@/components/auth/gates";
import { ExamModuleProvider } from "@/lib/exam/module";

export const metadata: Metadata = { title: "Reading" };

export default function ReadingPage() {
  return (
    <SignedIn path="/reading">
      <ExamModuleProvider module="reading">
        <ReadingHome />
      </ExamModuleProvider>
    </SignedIn>
  );
}
