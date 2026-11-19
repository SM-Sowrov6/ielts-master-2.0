"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { LoaderCircleIcon, MailCheckIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CheckboxField, PasswordField } from "@/components/auth/fields";
import { AuthHeading, FormError, ResultPanel } from "@/components/auth/status";
import { LoadingState } from "@/components/patterns/states";
import { FormTextField } from "@/components/patterns/form-text-field";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import {
  fetchRegistrationPolicy,
  fieldErrorsFrom,
  messageFor,
  register,
  resendVerification,
  type RegistrationPolicy,
} from "@/lib/auth/api";
import { queryKeys } from "@/lib/query/keys";

const schema = z.object({
  full_name: z.string().trim().min(1, "Enter your name.").max(100, "Use at most 100 characters."),
  email: z
    .string()
    .trim()
    .min(1, "Enter your email address.")
    .email("Enter a valid email address."),
  password: z
    .string()
    .min(10, "Use at least 10 characters.")
    .max(128, "Use at most 128 characters."),
  accept_terms: z
    .boolean()
    .refine((v) => v, "Accept the Terms of Service and Privacy Policy to continue."),
  age_confirmation: z.boolean().refine((v) => v, "Confirm the age requirement to continue."),
});
type Values = z.infer<typeof schema>;
const FIELDS = ["full_name", "email", "password", "accept_terms", "age_confirmation"] as const;

export function RegisterForm() {
  const policy = useQuery({
    queryKey: queryKeys.auth.registrationPolicy(),
    queryFn: fetchRegistrationPolicy,
    staleTime: 60_000,
  });
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  if (policy.isPending) return <LoadingState label="Loading registration…" rows={4} />;
  if (policy.isError) {
    return <FormError title="Registration is unavailable">{messageFor(policy.error)}</FormError>;
  }
  if (!policy.data.open) {
    return (
      <ResultPanel
        tone="neutral"
        title="Registration isn't open yet"
        actions={
          <Button asChild variant="outline" className="h-10">
            <Link href="/sign-in">Sign in to an existing account</Link>
          </Button>
        }
      >
        <p>New accounts can&apos;t be created at the moment. Please check back soon.</p>
      </ResultPanel>
    );
  }
  if (submittedEmail)
    return <CheckYourEmail email={submittedEmail} onReset={() => setSubmittedEmail(null)} />;
  return <RegistrationFields policy={policy.data} onRegistered={setSubmittedEmail} />;
}

function RegistrationFields({
  policy,
  onRegistered,
}: {
  policy: RegistrationPolicy;
  onRegistered: (email: string) => void;
}) {
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: "",
      email: "",
      password: "",
      accept_terms: false,
      age_confirmation: false,
    },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: Values) {
    setFormError(null);
    try {
      await register(values);
      onRegistered(values.email);
    } catch (error) {
      if (error instanceof ApiError && error.code === "password_policy") {
        form.setError(
          "password",
          { message: error.detail ?? error.message },
          { shouldFocus: true },
        );
        return;
      }
      const fieldErrors = fieldErrorsFrom(error);
      const known = FIELDS.filter((f) => f in fieldErrors);
      if (known.length > 0) {
        known.forEach((f, i) =>
          form.setError(f, { message: fieldErrors[f] }, { shouldFocus: i === 0 }),
        );
        return;
      }
      setFormError(messageFor(error));
    }
  }

  const placeholder = policy.development_placeholders;
  return (
    <div className="space-y-8">
      <AuthHeading
        title="Create your account"
        description="Start practising all four IELTS skills. It takes less than a minute."
      />
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        {formError && <FormError>{formError}</FormError>}
        {placeholder && (
          <p className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
            {policy.minimum_age === null
              ? "Development build: the age policy and legal documents below are placeholders pending approval. Public registration stays closed until they are confirmed."
              : "Development build: the Terms of Service and Privacy Policy are not published yet. Public registration stays closed until they are approved."}
          </p>
        )}
        <FormTextField
          control={form.control}
          name="full_name"
          label="Full name"
          autoComplete="name"
          className="h-10"
        />
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
          autoComplete="new-password"
          description="At least 10 characters. A short phrase is easy to remember and hard to guess."
        />
        <div className="space-y-3 pt-1">
          <CheckboxField control={form.control} name="accept_terms">
            I agree to the{" "}
            <Link href="/terms" target="_blank" className="underline">
              Terms of Service
            </Link>{" "}
            and{" "}
            <Link href="/privacy" target="_blank" className="underline">
              Privacy Policy
            </Link>
            {placeholder
              ? " (documents pending approval)"
              : ` (versions ${policy.terms_version} / ${policy.privacy_version})`}
            .
          </CheckboxField>
          <CheckboxField control={form.control} name="age_confirmation">
            {policy.minimum_age !== null
              ? `I confirm I am at least ${policy.minimum_age} years old.`
              : "I confirm I meet the minimum age requirement (age policy pending approval)."}
          </CheckboxField>
        </div>
        <Button type="submit" className="h-10 w-full text-[0.9375rem]" disabled={submitting}>
          {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          {submitting ? "Creating your account…" : "Create account"}
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
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

function CheckYourEmail({ email, onReset }: { email: string; onReset: () => void }) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  async function resend() {
    setState("sending");
    try {
      await resendVerification(email);
      setState("sent");
    } catch {
      setState("error");
    }
  }
  return (
    <ResultPanel
      icon={MailCheckIcon}
      title="Check your email"
      actions={
        <>
          <Button
            variant="outline"
            className="h-10"
            onClick={resend}
            disabled={state === "sending"}
          >
            {state === "sending" && (
              <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            )}
            Resend the email
          </Button>
          <Button variant="ghost" className="h-10" onClick={onReset}>
            Use a different email address
          </Button>
        </>
      }
    >
      <p>
        We&apos;ve sent a verification link to <strong className="text-foreground">{email}</strong>.
        Open it to activate your account, then sign in. The link expires in 24 hours.
      </p>
      <p>Can&apos;t find it? Check your spam folder.</p>
      {state === "sent" && <p className="text-success">A new link is on its way.</p>}
      {state === "error" && (
        <p className="text-destructive">We couldn&apos;t resend right now. Try again shortly.</p>
      )}
    </ResultPanel>
  );
}
