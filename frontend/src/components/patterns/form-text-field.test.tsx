import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { FormTextField } from "@/components/patterns/form-text-field";
import { axeViolations } from "@/test/axe";

const schema = z.object({ name: z.string().min(2, "Enter at least 2 characters.") });

function TestForm({ onValid }: { onValid: (values: z.infer<typeof schema>) => void }) {
  const form = useForm({ resolver: zodResolver(schema), defaultValues: { name: "" } });
  return (
    <form noValidate onSubmit={form.handleSubmit(onValid)}>
      <FormTextField
        control={form.control}
        name="name"
        label="Display name"
        description="Shown to you only."
      />
      <button type="submit">Save</button>
    </form>
  );
}

describe("FormTextField", () => {
  it("labels the control and links its description", async () => {
    const { container } = render(<TestForm onValid={vi.fn()} />);
    const input = screen.getByLabelText("Display name");
    expect(input).toHaveAccessibleDescription("Shown to you only.");
    expect(input).not.toHaveAttribute("aria-invalid");
    expect(await axeViolations(container)).toEqual([]);
  });

  it("announces validation errors on the control and only submits valid data", async () => {
    const user = userEvent.setup();
    const onValid = vi.fn();
    const { container } = render(<TestForm onValid={onValid} />);
    await user.click(screen.getByRole("button", { name: "Save" }));

    const input = screen.getByLabelText("Display name");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(
      expect.stringContaining("Enter at least 2 characters."),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Enter at least 2 characters.");
    expect(onValid).not.toHaveBeenCalled();
    expect(await axeViolations(container)).toEqual([]);

    await user.type(input, "Sam");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onValid).toHaveBeenCalledWith({ name: "Sam" }, expect.anything());
  });
});
