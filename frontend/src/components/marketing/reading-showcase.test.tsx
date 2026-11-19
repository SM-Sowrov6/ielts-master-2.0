import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEMO_ANSWER, ReadingDemo } from "@/components/marketing/reading-demo";
import { ReadingShowcase } from "@/components/marketing/reading-showcase";
import { axeViolations } from "@/test/axe";

const FOCUSABLE = "a, button, input, select, textarea, summary, [tabindex], [contenteditable]";

function mockReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

const field = () => document.querySelector<HTMLElement>(".rx-field");
const selection = () => document.querySelector(".rx-selection")?.textContent ?? "";

beforeEach(() => {
  document.documentElement.lang = "en";
  mockReducedMotion(false);
});
afterEach(() => {
  vi.useRealTimers();
});

describe("ReadingShowcase (Module 02)", () => {
  it("keeps the anchor and heading, and its call to action is honest", () => {
    render(<ReadingShowcase />);
    const section = document.getElementById("reading");
    expect(section).toHaveAttribute("aria-labelledby", "reading-heading");
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Read Smarter. Understand Deeper.",
    );
    expect(screen.getByText("Module 02 · Reading")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Explore Reading" })).toHaveAttribute(
      "href",
      "/reading",
    );
  });

  it("the display is decorative, without controls, and described once", () => {
    const { container } = render(<ReadingShowcase />);
    const stage = container.querySelector("[data-decorative]");
    expect(stage).toHaveAttribute("aria-hidden", "true");
    expect(stage).toHaveAttribute("inert");
    expect(stage?.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    expect(container.querySelectorAll(".rx-rim").length).toBeGreaterThan(0);
    expect(screen.getByText(/^Illustration: a large screen showing/)).toHaveClass("sr-only");
  });

  it("plays the demo: select the phrase, focus the field, type, save, then loop", async () => {
    vi.useFakeTimers();
    render(<ReadingDemo />);
    expect(field()?.textContent).toBe("");

    await act(() => vi.advanceTimersByTimeAsync(2700)); // move + start selecting
    expect(selection().length).toBeGreaterThan(0);
    expect("artificial light".startsWith(selection())).toBe(true);

    await act(() => vi.advanceTimersByTimeAsync(3500)); // selection done, moved, clicked
    expect(selection()).toBe("");
    expect(document.querySelector(".rx-highlight")).not.toBeNull();
    expect(field()?.dataset.focused).toBe("true");

    await act(() => vi.advanceTimersByTimeAsync(900)); // typing has started, not finished
    const partial = field()?.textContent ?? "";
    expect(partial.length).toBeGreaterThan(0);
    expect(partial.length).toBeLessThan(DEMO_ANSWER.length);
    expect(DEMO_ANSWER.startsWith(partial)).toBe(true);

    await act(() => vi.advanceTimersByTimeAsync(2600)); // typed and saved
    expect(field()?.textContent).toBe(DEMO_ANSWER);
    expect(field()?.dataset.saved).toBe("true");
    expect(screen.getByText("19 / 40 answered")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(3800)); // reset for the next loop
    expect(field()?.textContent).toBe("");
    expect(field()?.dataset.saved).toBe("false");
  });

  it("shows the finished state without motion when reduced motion is requested", () => {
    mockReducedMotion(true);
    render(<ReadingDemo />);
    expect(field()?.textContent).toBe(DEMO_ANSWER);
    expect(field()?.dataset.saved).toBe("true");
    expect(document.querySelector<HTMLElement>(".rx-cursor")?.style.opacity).toBe("0");
  });

  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<ReadingShowcase />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
