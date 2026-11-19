"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircleIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { PasswordField } from "@/components/auth/fields";
import { FormError } from "@/components/auth/status";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { changePassword, messageFor, signOutEverywhere } from "@/lib/auth/api";
import { useSetCurrentUser } from "@/lib/auth/hooks";

const schema = z
  .object({
    current: z.string().min(1, "Enter your current password."),
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
type Values = z.infer<typeof schema>;

export function ChangePasswordForm() {
  const router = useRouter();
  const setCurrentUser = useSetCurrentUser();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { current: "", password: "", confirm: "" },
  });
  const submitting = form.formState.isSubmitting;

  async function onSubmit(values: Values) {
    setFormError(null);
    try {
      await changePassword(values.current, values.password);
      form.reset();
      toast.success("Password changed", {
        description: "Other devices have been signed out. You're still signed in here.",
      });
    } catch (error) {
      if (error instanceof ApiError && error.code === "current_password_incorrect") {
        form.setError(
          "current",
          { message: "Your current password is incorrect." },
          { shouldFocus: true },
        );
      } else if (error instanceof ApiError && error.code === "password_policy") {
        form.setError(
          "password",
          { message: error.detail ?? error.message },
          { shouldFocus: true },
        );
      } else {
        setFormError(messageFor(error));
      }
    }
  }

  async function signOutAll() {
    await signOutEverywhere();
    setCurrentUser(null);
    router.push("/sign-in");
    router.refresh();
  }

  return (
    <div className="max-w-md space-y-10">
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        {formError && <FormError>{formError}</FormError>}
        <PasswordField
          control={form.control}
          name="current"
          label="Current password"
          autoComplete="current-password"
        />
        <PasswordField
          control={form.control}
          name="password"
          label="New password"
          autoComplete="new-password"
          description="At least 10 characters. Changing it signs out your other devices."
        />
        <PasswordField
          control={form.control}
          name="confirm"
          label="Repeat new password"
          autoComplete="new-password"
        />
        <Button type="submit" className="h-10" disabled={submitting}>
          {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          Change password
        </Button>
      </form>
      <section aria-labelledby="sessions-heading" className="space-y-3 border-t pt-8">
        <h2 id="sessions-heading" className="font-heading text-base font-semibold">
          Signed-in devices
        </h2>
        <p className="text-sm text-muted-foreground">
          Lost a device or signed in on a shared computer? Sign out everywhere, including here.
        </p>
        <ConfirmDialog
          trigger={<Button variant="outline">Sign out of all devices</Button>}
          title="Sign out of all devices?"
          description="You'll need to sign in again on every device, including this one."
          confirmLabel="Sign out everywhere"
          onConfirm={signOutAll}
        />
      </section>
    </div>
  );
}
