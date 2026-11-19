import type { Metadata } from "next";

import { AttemptHistory } from "@/components/listening/attempt-history";
import { SignedIn } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Listening attempts" };

export default function ListeningHistoryPage() {
  return (
    <SignedIn path="/listening/history">
      <AttemptHistory />
    </SignedIn>
  );
}
