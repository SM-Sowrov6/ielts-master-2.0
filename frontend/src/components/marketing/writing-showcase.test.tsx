import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEMO_TEXT, DEMO_WORDS, WritingDemo, keysFor } from "@/components/marketing/writing-demo";
import { WritingShowcase } from "@/components/marketing/writing-showcase";
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

/** Text in the editor, paragraphs joined by "\n" (as typed). */
const editorText = () =>
  [...document.querySelectorAll(".wx-editor p")].map((p) => p.textContent ?? "").join("\n");
const downKeys = () =>
  [...document.querySelectorAll<HTMLElement>('.wx-key[data-down="true"]')].map(
    (k) => k.dataset.key,
  );
const words = () => Number.parseInt(document.querySelector(".wx-count")?.textContent ?? "", 10);
const bot = () => document.querySelector<HTMLElement>(".wx-bot");

beforeEach(() => {
  document.documentElement.lang = "en";
  mockReducedMotion(false);
});
afterEach(() => {
  vi.useRealTimers();
});

describe("WritingShowcase (Module 03)", () => {
  it("keeps the anchor and heading, and its call to action is honest", () => {
    render(<WritingShowcase />);
    expect(document.getElementById("writing")).toHaveAttribute(
      "aria-labelledby",
      "writing-heading",
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Write with Confidence. Achieve More.",
    );
    expect(screen.getByText("Module 03 · Writing")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Explore Writing" })).toHaveAttribute(
      "href",
      "/writing",
    );
  });

  it("the MacBook is decorative, has a full keyboard and the mascot, and no controls", () => {
    const { container } = render(<WritingShowcase />);
    const stage = container.querySelector("[data-decorative]");
    expect(stage).toHaveAttribute("aria-hidden", "true");
    expect(stage).toHaveAttribute("inert");
    expect(stage?.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    for (const ch of new Set(DEMO_TEXT)) {
      for (const id of keysFor(ch)) {
        expect(stage?.querySelector(`.wx-key[data-key="${CSS.escape(id)}"]`)).not.toBeNull();
      }
    }
    expect(stage?.querySelector(".wx-lid .wx-bot")).not.toBeNull();
  });

  it("maps characters to the keys that type them", () => {
    expect(keysFor("a")).toEqual(["a"]);
    expect(keysFor("R")).toEqual(["r", "shiftL"]);
    expect(keysFor(" ")).toEqual(["space"]);
    expect(keysFor("\n")).toEqual(["return"]);
    expect(keysFor(".")).toEqual(["."]);
  });

  it("types with the keyboard: each key press adds its character, the word count follows", async () => {
    vi.useFakeTimers();
    render(<WritingDemo />);
    expect(editorText()).toBe("");
    expect(words()).toBe(0);

    await act(() => vi.advanceTimersByTimeAsync(1690)); // wake + mascot turns to the editor
    expect(bot()?.dataset.mood).toBe("watching");

    // Step through the first characters: the pressed key is the one for the last character.
    let checked = 0;
    for (let step = 0; step < 400 && checked < 12; step += 1) {
      await act(() => vi.advanceTimersByTimeAsync(5));
      const text = editorText();
      const keys = downKeys();
      if (text.length > 0 && keys.length > 0) {
        expect(keys).toEqual(keysFor(text.at(-1) ?? ""));
        expect(DEMO_TEXT.startsWith(text)).toBe(true);
        checked += 1;
      }
    }
    expect(checked).toBe(12);

    await act(() => vi.advanceTimersByTimeAsync(3000)); // more typing, the count rises
    const mid = words();
    expect(mid).toBeGreaterThan(0);
    expect(mid).toBeLessThan(DEMO_WORDS);

    await act(() => vi.advanceTimersByTimeAsync(17_000)); // both paragraphs typed
    expect(editorText()).toBe(DEMO_TEXT);
    expect(words()).toBe(DEMO_WORDS);
    expect(document.querySelectorAll(".wx-editor p")).toHaveLength(2);
    expect(bot()?.dataset.mood).toBe("done");
    expect(document.querySelector(".wx-float-grammar")).toHaveAttribute("data-show", "true");

    await act(() => vi.advanceTimersByTimeAsync(4500)); // hold, fade, replay from the start
    expect(words()).toBeLessThan(DEMO_WORDS);
    expect(DEMO_TEXT.startsWith(editorText())).toBe(true);
  });

  it("shows the finished essay without motion when reduced motion is requested", () => {
    mockReducedMotion(true);
    render(<WritingDemo />);
    expect(editorText()).toBe(DEMO_TEXT);
    expect(words()).toBe(DEMO_WORDS);
    expect(downKeys()).toEqual([]);
    expect(bot()?.dataset.mood).toBe("done");
  });

  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<WritingShowcase />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
