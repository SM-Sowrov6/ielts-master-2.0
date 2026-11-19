import type { Metadata } from "next";

import { redirectIfSignedIn } from "@/app/(auth)/redirect-if-signed-in";
import { SignInForm } from "@/components/auth/sign-in-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string | string[] }>;
}) {
  const { next } = await searchParams;
  const target = typeof next === "string" ? next : undefined;
  await redirectIfSignedIn(target);
  return <SignInForm next={target} />;
}
