"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  KeyRoundIcon,
  LinkIcon,
  LoaderCircleIcon,
  MailCheckIcon,
  MailWarningIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { PasswordField } from "@/components/auth/fields";
import { AuthHeading, FormError, ResultPanel } from "@/components/auth/status";
import { FormTextField } from "@/components/patterns/form-text-field";
import { LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import {
  messageFor,
  requestPasswordReset,
  resendVerification,
  resetPassword,
  verifyEmail,
} from "@/lib/auth/api";

const emailSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Enter your email address.")
    .email("Enter a valid email address."),
});
type EmailValues = z.infer<typeof emailSchema>;

const newPasswordSchema = z
  .object({
    password: z
      .string()
      .min(10, "Use at least 10 characters.")
      .max(128, "Use at most 128 characters."),
    confirm: z.string().min(1, "Repeat your new password."),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "The passwords don't match.",
  });
type NewPasswordValues = z.infer<typeof newPasswordSchema>;

/**
 * Read the one-time token from the URL fragment (`#token=…`) and immediately remove it from the
 * address bar and history, so it is not left on screen, in bookmarks or in shared links.
 * Fragments are never sent to servers or in Referer headers.
 */
const TOKEN_SHAPE = /^[A-Za-z0-9_-]{43}$/;
const PENDING = "pending:server"; // never a valid token (tokens are 43 URL-safe chars)
let capturedToken: string | undefined;

function readFragmentToken(): string {
  const fromHash = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
  if (fromHash !== null) capturedToken = TOKEN_SHAPE.test(fromHash) ? fromHash : "";
  return capturedToken ?? "";
}

const noSubscription = () => () => undefined;

function useFragmentToken(): { ready: boolean; token: string | null } {
  // Server render: "pending"; client: the captured token ("" when absent or malformed).
  const value = useSyncExternalStore(noSubscription, readFragmentToken, () => PENDING);
  useEffect(() => {
    // Capture first, then clear the address bar on the next task. React may re-read the snapshot
    // after hydration, and StrictMode re-runs effects: the cleanup cancels a pending strip and
    // forgets the token, so the re-run (and any later visit without a token) starts clean.
    readFragmentToken();
    const strip = window.setTimeout(() => {
      if (window.location.hash) {
        window.history.replaceState(
          window.history.state,
          "",
          window.location.pathname + window.location.search,
        );
      }
    }, 0);
    return () => {
      window.clearTimeout(strip);
      capturedToken = undefined;
    };
  }, []);
  return { ready: value !== PENDING, token: value && value !== PENDING ? value : null };
}

// --- Forgot password ----------------------------------------------------------------------------
export function ForgotPasswordForm() {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<EmailValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: "" },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: EmailValues) {
    setFormError(null);
    try {
      await requestPasswordReset(values.email);
      setSentTo(values.email);
    } catch (error) {
      setFormError(messageFor(error));
    }
  }

  if (sentTo) {
    return (
      <ResultPanel
        icon={MailCheckIcon}
        title="Check your email"
        actions={
          <Button asChild variant="outline" className="h-10">
            <Link href="/sign-in">Back to sign in</Link>
          </Button>
        }
      >
        <p>
          If an account exists for <strong className="text-foreground">{sentTo}</strong>, we&apos;ve
          sent a link to reset its password. The link expires in 30 minutes.
        </p>
        <p>Can&apos;t find it? Check your spam folder, or try again in a few minutes.</p>
      </ResultPanel>
    );
  }
  return (
    <div className="space-y-8">
      <AuthHeading
        title="Reset your password"
        description="Enter the email address for your account and we'll send you a link to choose a new password."
      />
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        {formError && <FormError>{formError}</FormError>}
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
        <Button type="submit" className="h-10 w-full text-[0.9375rem]" disabled={submitting}>
          {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          Send reset link
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        Remembered it?{" "}
        <Link
          href="/sign-in"
          className="rounded-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}

// --- Reset password -----------------------------------------------------------------------------
export function ResetPasswordForm() {
  const { ready, token } = useFragmentToken();
  const [outcome, setOutcome] = useState<"done" | "invalid" | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<NewPasswordValues>({
    resolver: zodResolver(newPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: NewPasswordValues) {
    if (!token) return;
    setFormError(null);
    try {
      await resetPassword(token, values.password);
      setOutcome("done");
    } catch (error) {
      if (error instanceof ApiError && error.code === "token_invalid") setOutcome("invalid");
      else if (error instanceof ApiError && error.code === "password_policy")
        form.setError(
          "password",
          { message: error.detail ?? error.message },
          { shouldFocus: true },
        );
      else setFormError(messageFor(error));
    }
  }

  if (!ready) return <LoadingState label="Checking your link…" rows={2} />;
  if (outcome === "done") {
    return (
      <ResultPanel
        icon={KeyRoundIcon}
        title="Password updated"
        actions={
          <Button asChild className="h-10">
            <Link href="/sign-in">Sign in</Link>
          </Button>
        }
      >
        <p>
          Your password has been changed and every device was signed out. Sign in with your new
          password.
        </p>
      </ResultPanel>
    );
  }
  if (!token || outcome === "invalid") return <ExpiredLink kind="reset" />;
  return (
    <div className="space-y-8">
      <AuthHeading
        title="Choose a new password"
        description="Use at least 10 characters. You'll sign in again afterwards."
      />
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        {formError && <FormError>{formError}</FormError>}
        <PasswordField
          control={form.control}
          name="password"
          label="New password"
          autoComplete="new-password"
        />
        <PasswordField
          control={form.control}
          name="confirm"
          label="Repeat new password"
          autoComplete="new-password"
        />
        <Button type="submit" className="h-10 w-full text-[0.9375rem]" disabled={submitting}>
          {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          Update password
        </Button>
      </form>
    </div>
  );
}

// --- Verify email -------------------------------------------------------------------------------
export function VerifyEmail() {
  const { ready, token } = useFragmentToken();
  const [state, setState] = useState<"verifying" | "verified" | "invalid" | "error">("verifying");
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (!ready || !token || started.current) return;
    started.current = true; // the token is single-use: submit it exactly once
    verifyEmail(token)
      .then(() => setState("verified"))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.code === "token_invalid") setState("invalid");
        else {
          setError(messageFor(err));
          setState("error");
        }
      });
  }, [ready, token]);

  if (ready && !token) return <ExpiredLink kind="verify" />;
  if (state === "verifying") return <LoadingState label="Verifying your email address…" rows={2} />;
  if (state === "verified") {
    return (
      <ResultPanel
        title="Email verified"
        actions={
          <Button asChild className="h-10">
            <Link href="/sign-in">Sign in</Link>
          </Button>
        }
      >
        <p>
          Thanks for confirming your email address. Your account is active. Sign in to get started.
        </p>
      </ResultPanel>
    );
  }
  if (state === "error") {
    return (
      <ResultPanel
        icon={MailWarningIcon}
        tone="error"
        title="We couldn't verify your email"
        actions={
          <Button className="h-10" onClick={() => window.location.reload()}>
            Try again
          </Button>
        }
      >
        <p>{error}</p>
      </ResultPanel>
    );
  }
  return <ExpiredLink kind="verify" />;
}

function ExpiredLink({ kind }: { kind: "verify" | "reset" }) {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<EmailValues>({
    resolver: zodResolver(emailSchema),
    defaultValues: { email: "" },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: EmailValues) {
    setFormError(null);
    try {
      if (kind === "verify") await resendVerification(values.email);
      else await requestPasswordReset(values.email);
      setSentTo(values.email);
    } catch (error) {
      setFormError(messageFor(error));
    }
  }

  return (
    <ResultPanel
      icon={LinkIcon}
      tone="error"
      title="This link is invalid or has expired"
      actions={
        sentTo ? (
          <Button asChild variant="outline" className="h-10">
            <Link href="/sign-in">Back to sign in</Link>
          </Button>
        ) : (
          <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {formError && <FormError>{formError}</FormError>}
            <FormTextField
              control={form.control}
              name="email"
              label="Email address"
              type="email"
              autoComplete="email"
              className="h-10"
            />
            <Button type="submit" className="h-10 w-full" disabled={submitting}>
              {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
              {kind === "verify" ? "Send a new verification link" : "Send a new reset link"}
            </Button>
          </form>
        )
      }
    >
      <p>
        Links can be used once and expire after {kind === "verify" ? "24 hours" : "30 minutes"}.
        Newer links replace older ones.
      </p>
      {sentTo ? (
        <p className="text-success">
          If the account needs it, a new link is on its way to {sentTo}.
        </p>
      ) : (
        <p>Enter your email address and we&apos;ll send a new one.</p>
      )}
    </ResultPanel>
  );
}
