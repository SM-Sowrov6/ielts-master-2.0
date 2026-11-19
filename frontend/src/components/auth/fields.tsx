"use client";

import { EyeIcon, EyeOffIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Controller, type Control, type FieldPath, type FieldValues } from "react-hook-form";

import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

/**
 * Password input with a show/hide toggle. The toggle is a real button with `aria-pressed`, so
 * screen-reader users know the state; the value is never logged or stored by the page.
 */
export function PasswordField<T extends FieldValues>({
  control,
  name,
  label,
  description,
  autoComplete,
  labelAction,
}: {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  description?: string;
  autoComplete: "current-password" | "new-password";
  labelAction?: ReactNode;
}) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const invalid = fieldState.invalid;
        const describedBy =
          [description ? `${id}-description` : null, invalid ? `${id}-error` : null]
            .filter(Boolean)
            .join(" ") || undefined;
        return (
          <Field data-invalid={invalid || undefined}>
            <div className="flex items-center justify-between gap-2">
              <FieldLabel htmlFor={id}>{label}</FieldLabel>
              {labelAction}
            </div>
            <div className="relative">
              <Input
                {...field}
                value={(field.value as string | undefined) ?? ""}
                id={id}
                type={visible ? "text" : "password"}
                autoComplete={autoComplete}
                spellCheck={false}
                autoCapitalize="none"
                aria-invalid={invalid || undefined}
                aria-describedby={describedBy}
                className="h-10 pr-11"
              />
              <button
                type="button"
                onClick={() => setVisible((v) => !v)}
                aria-pressed={visible}
                aria-label={visible ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-lg text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
              >
                {visible ? (
                  <EyeOffIcon className="size-4" aria-hidden="true" />
                ) : (
                  <EyeIcon className="size-4" aria-hidden="true" />
                )}
              </button>
            </div>
            {description && (
              <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
            )}
            {invalid && <FieldError id={`${id}-error`} errors={[fieldState.error]} />}
          </Field>
        );
      }}
    />
  );
}

export function CheckboxField<T extends FieldValues>({
  control,
  name,
  children,
}: {
  control: Control<T>;
  name: FieldPath<T>;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => (
        <Field data-invalid={fieldState.invalid || undefined}>
          <div className="flex items-start gap-3">
            <Checkbox
              id={id}
              checked={field.value === true}
              onCheckedChange={(checked) => field.onChange(checked === true)}
              onBlur={field.onBlur}
              ref={field.ref}
              aria-invalid={fieldState.invalid || undefined}
              aria-describedby={fieldState.invalid ? `${id}-error` : undefined}
              className="mt-0.5"
            />
            <FieldLabel htmlFor={id} className="text-sm leading-snug font-normal">
              {children}
            </FieldLabel>
          </div>
          {fieldState.invalid && <FieldError id={`${id}-error`} errors={[fieldState.error]} />}
        </Field>
      )}
    />
  );
}
