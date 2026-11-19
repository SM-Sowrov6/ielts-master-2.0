"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircleIcon, MailCheckIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordField } from "@/components/auth/fields";
import { AuthHeading, FormError } from "@/components/auth/status";
import { FormTextField } from "@/components/patterns/form-text-field";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { messageFor, resendVerification, signIn } from "@/lib/auth/api";
import { useSetCurrentUser } from "@/lib/auth/hooks";
import { destinationAfterSignIn } from "@/lib/auth/redirect";

const schema = z.object({
  email: z.string().trim().min(1, "Enter your email address."),
  password: z.string().min(1, "Enter your password."),
});
type Values = z.infer<typeof schema>;

type Problem = { kind: "error"; message: string } | { kind: "unverified" } | { kind: "resent" };

export function SignInForm({ next }: { next?: string }) {
  const router = useRouter();
  const setCurrentUser = useSetCurrentUser();
  const [problem, setProblem] = useState<Problem | null>(null);
  const [resending, setResending] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: Values) {
    setProblem(null);
    try {
      const user = await signIn(values.email, values.password);
      setCurrentUser(user);
      router.replace(destinationAfterSignIn(user, next));
      router.refresh();
    } catch (error) {
      if (error instanceof ApiError && error.code === "email_not_verified") {
        setProblem({ kind: "unverified" });
      } else {
        setProblem({ kind: "error", message: messageFor(error) });
      }
      form.resetField("password");
    }
  }

  async function resend() {
    setResending(true);
    try {
      await resendVerification(form.getValues("email"));
      setProblem({ kind: "resent" });
    } catch (error) {
      setProblem({ kind: "error", message: messageFor(error) });
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="space-y-8">
      <AuthHeading title="Welcome back" description="Sign in to continue your IELTS preparation." />
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        {problem?.kind === "error" && <FormError>{problem.message}</FormError>}
        {problem?.kind === "unverified" && (
          <FormError title="Verify your email address first">
            <p>Open the link we emailed you to activate your account.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={resend}
              disabled={resending}
            >
              {resending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
              Send a new verification link
            </Button>
          </FormError>
        )}
        {problem?.kind === "resent" && (
          <div
            role="status"
            className="flex items-start gap-2 rounded-lg border border-success/30 bg-success/10 px-3 py-2.5 text-sm text-success"
          >
            <MailCheckIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            If your account still needs verifying, a new link is on its way. Check your inbox.
          </div>
        )}
        <FormTextField
          control={form.control}
          name="email"
          label="Email address"
          type="email"
          autoComplete="email"
          inputMode="email"
          spellCheck={false}
          className="h-10"
        />
        <PasswordField
          control={form.control}
          name="password"
          label="Password"
          autoComplete="current-password"
          labelAction={
            <Link
              href="/forgot-password"
              className="rounded-sm text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              Forgot password?
            </Link>
          }
        />
        <Button type="submit" className="h-10 w-full text-[0.9375rem]" disabled={submitting}>
          {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        New to IELTS MASTER?{" "}
        <Link
          href="/register"
          className="rounded-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Create an account
        </Link>
      </p>
    </div>
  );
}
