import type { Metadata } from "next";

import { VerifyEmail } from "@/components/auth/recovery-forms";

export const metadata: Metadata = { title: "Verify your email" };

export default function VerifyEmailPage() {
  return <VerifyEmail />;
}
