"use client";

import { useId, type ComponentProps } from "react";
import { Controller, type Control, type FieldPath, type FieldValues } from "react-hook-form";

import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type FormTextFieldProps<T extends FieldValues> = {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  description?: string;
  multiline?: boolean;
} & Omit<ComponentProps<"input">, "name" | "defaultValue" | "value" | "onChange" | "onBlur">;

/**
 * The form convention: React Hook Form owns state, a Zod schema (via `zodResolver`) validates,
 * and this component wires label, description and error message to the control
 * (`aria-invalid`, `aria-describedby`) so assistive technology announces them.
 */
export function FormTextField<T extends FieldValues>({
  control,
  name,
  label,
  description,
  multiline = false,
  id,
  ...inputProps
}: FormTextFieldProps<T>) {
  const generatedId = useId();
  const controlId = id ?? generatedId;
  const descriptionId = `${controlId}-description`;
  const errorId = `${controlId}-error`;

  return (
    <Controller
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const invalid = fieldState.invalid;
        const describedBy =
          [description ? descriptionId : null, invalid ? errorId : null]
            .filter(Boolean)
            .join(" ") || undefined;
        const shared = {
          ...field,
          value: (field.value as string | undefined) ?? "",
          id: controlId,
          "aria-invalid": invalid || undefined,
          "aria-describedby": describedBy,
        };
        return (
          <Field data-invalid={invalid || undefined}>
            <FieldLabel htmlFor={controlId}>{label}</FieldLabel>
            {multiline ? (
              <Textarea
                {...shared}
                placeholder={inputProps.placeholder}
                disabled={inputProps.disabled}
              />
            ) : (
              <Input {...inputProps} {...shared} />
            )}
            {description && <FieldDescription id={descriptionId}>{description}</FieldDescription>}
            {invalid && <FieldError id={errorId} errors={[fieldState.error]} />}
          </Field>
        );
      }}
    />
  );
}
