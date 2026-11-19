import type { Metadata } from "next";

import { ChangePasswordForm } from "@/components/auth/change-password-form";
import { SignedIn } from "@/components/auth/gates";
import { PageHeader } from "@/components/patterns/page-header";

export const metadata: Metadata = { title: "Change password", robots: { index: false } };

export default function ChangePasswordPage() {
  return (
    <SignedIn path="/account/password">
      <PageHeader
        title="Change password"
        description="Keep your account secure with a strong, unique password."
      />
      <ChangePasswordForm />
    </SignedIn>
  );
}
