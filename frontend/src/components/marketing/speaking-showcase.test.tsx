import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CONVERSATION, SpeakingDemo } from "@/components/marketing/speaking-demo";
import { SpeakingShowcase } from "@/components/marketing/speaking-showcase";
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

const turn = () => document.querySelector<HTMLElement>(".sx-demo")?.dataset.turn;
const bubbles = () =>
  [...document.querySelectorAll<HTMLElement>(".sx-bubble")].map((b) => ({
    who: b.dataset.who,
    text: b.querySelector(".sx-bubble-text")?.textContent ?? "",
    live: b.dataset.live,
  }));
const status = () => document.querySelector(".sx-status")?.textContent;

/** Advance in small steps until `check` passes (or fail after `limit` ms). */
async function until(check: () => boolean, limit = 30_000) {
  for (let t = 0; t < limit && !check(); t += 50) {
    await act(() => vi.advanceTimersByTimeAsync(50));
  }
  expect(check()).toBe(true);
}

beforeEach(() => {
  document.documentElement.lang = "en";
  mockReducedMotion(false);
});
afterEach(() => {
  vi.useRealTimers();
});

describe("SpeakingShowcase (Module 04)", () => {
  it("has the agreed label, headline, description and an honest call to action", () => {
    render(<SpeakingShowcase />);
    expect(document.getElementById("speaking")).toHaveAttribute(
      "aria-labelledby",
      "speaking-heading",
    );
    expect(screen.getByText("Module 04 · Speaking")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent(
      "Speak Naturally. Speak Confidently.",
    );
    expect(
      screen.getByText(/^Build your speaking confidence with an intelligent AI speaking partner\./),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Explore Speaking" })).toHaveAttribute(
      "href",
      "/speaking",
    );
  });

  it("the scene is decorative: avatar, microphone, two waveforms, no controls", () => {
    const { container } = render(<SpeakingShowcase />);
    const stage = container.querySelector("[data-decorative]");
    expect(stage).toHaveAttribute("aria-hidden", "true");
    expect(stage).toHaveAttribute("inert");
    expect(stage?.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    expect(stage?.querySelector(".sx-avatar")).not.toBeNull();
    expect(stage?.querySelector(".sx-mic")).not.toBeNull();
    expect(stage?.querySelector('.sx-wave[data-tone="ai"]')).not.toBeNull();
    expect(stage?.querySelector('.sx-wave[data-tone="you"]')).not.toBeNull();
    expect(stage).toHaveTextContent("Your Turn");
    expect(screen.getByText(/^Illustration: an AI speaking partner/)).toHaveClass("sr-only");
  });

  it("runs one synchronised exchange: partner speaks, hand-over, student answers, loop", async () => {
    vi.useFakeTimers();
    render(<SpeakingDemo />);
    expect(turn()).toBe("idle");
    expect(bubbles()).toEqual([]);

    // 1–4: the partner speaks; its bubble fills word by word while its state is "ai".
    await until(() => turn() === "ai" && (bubbles()[0]?.text.split(" ").length ?? 0) >= 3);
    const partial = bubbles()[0];
    expect(partial?.who).toBe("ai");
    expect(partial?.live).toBe("true");
    expect(CONVERSATION[0]?.text.startsWith(partial?.text ?? "x")).toBe(true);
    expect(partial?.text.length).toBeLessThan(CONVERSATION[0]?.text.length ?? 0);
    expect(status()).toBe("AI partner is speaking");

    // 5: hand-over — the full question is shown and the microphone is next.
    await until(() => turn() === "handoff");
    expect(bubbles()[0]?.text).toBe(CONVERSATION[0]?.text);
    expect(bubbles()).toHaveLength(1);

    // 6–8: the student answers word by word.
    await until(() => turn() === "you" && (bubbles()[1]?.text.length ?? 0) > 0);
    expect(bubbles()[1]?.who).toBe("you");
    expect(bubbles()[0]?.live).toBe("false");
    expect(status()).toBe("Listening to you");

    // 9: complete, then back to the beginning.
    await until(() => turn() === "done");
    expect(bubbles().map(({ who, text }) => ({ who, text }))).toEqual(
      CONVERSATION.map(({ who, text }) => ({ who, text })),
    );
    await until(() => turn() === "idle" && bubbles().length === 0, 8000);
  });

  it("shows the finished exchange without motion when reduced motion is requested", () => {
    mockReducedMotion(true);
    render(<SpeakingDemo />);
    expect(bubbles().map(({ who, text }) => ({ who, text }))).toEqual(
      CONVERSATION.map(({ who, text }) => ({ who, text })),
    );
    expect(turn()).toBe("done");
  });

  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<SpeakingShowcase />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
