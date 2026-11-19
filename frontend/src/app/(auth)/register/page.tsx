import type { Metadata } from "next";

import { redirectIfSignedIn } from "@/app/(auth)/redirect-if-signed-in";
import { RegisterForm } from "@/components/auth/register-form";

export const metadata: Metadata = { title: "Create your account" };

export default async function RegisterPage() {
  await redirectIfSignedIn();
  return <RegisterForm />;
}
