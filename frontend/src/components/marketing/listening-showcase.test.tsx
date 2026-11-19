import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ListeningShowcase } from "@/components/marketing/listening-showcase";
import { axeViolations } from "@/test/axe";

const FOCUSABLE = "a, button, input, select, textarea, summary, [tabindex], [contenteditable]";

beforeEach(() => {
  document.documentElement.lang = "en";
});

describe("ListeningShowcase (Module 01)", () => {
  it("keeps the section anchor, heading and layout contract", () => {
    render(<ListeningShowcase />);
    const section = document.getElementById("listening");
    expect(section).toHaveAttribute("aria-labelledby", "listening-heading");
    expect(section).toHaveAttribute("data-visual-side", "right");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Master IELTS Listening");
    expect(screen.getByText("Module 01 · Listening")).toBeInTheDocument();
  });

  it("calls to action are honest about availability", () => {
    render(<ListeningShowcase />);
    expect(screen.getByRole("link", { name: "Explore Listening" })).toHaveAttribute(
      "href",
      "/listening",
    );
    expect(screen.getByRole("link", { name: "Create your account" })).toHaveAttribute(
      "href",
      "/register",
    );
  });

  it("builds a 3D MacBook whose screen is decorative and contains no controls", () => {
    const { container } = render(<ListeningShowcase />);
    const stage = container.querySelector("[data-decorative]");
    expect(stage).toHaveAttribute("aria-hidden", "true");
    expect(stage).toHaveAttribute("inert");
    expect(stage?.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    for (const part of [
      ".lx-lid",
      ".lx-screen",
      ".lx-base",
      ".lx-keys",
      ".lx-trackpad",
      ".lx-hp",
    ]) {
      expect(container.querySelector(part)).not.toBeNull();
    }
    expect(container.querySelectorAll(".lx-rim")).toHaveLength(8); // rounded unibody edge
    expect(screen.getByText(/^Illustration: a laptop showing/)).toHaveClass("sr-only");
  });

  // The device is built from many small decorative elements; axe needs longer than the default.
  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<ListeningShowcase />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
