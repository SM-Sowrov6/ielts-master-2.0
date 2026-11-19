import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COACH_MESSAGE, CoachDemo, STUDENT_MESSAGE } from "@/components/marketing/coach-demo";
import { CoachSection } from "@/components/marketing/coach-section";
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

const mood = () => document.querySelector<HTMLElement>(".cx-demo")?.dataset.mood;
const studentText = () =>
  document.querySelector('.cx-msg[data-from="student"] .cx-bubble')?.textContent ?? "";
const coachText = () => document.querySelector(".cx-coach-text")?.textContent ?? "";
const typing = () => document.querySelector(".cx-typing") !== null;
const feedbackShown = () => document.querySelector(".cx-feedback")?.getAttribute("data-show");
const recsShown = () => document.querySelectorAll('.cx-rec[data-show="true"]').length;

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

describe("CoachSection (AI Coach)", () => {
  it("has the agreed eyebrow, headline, description and an honest call to action", () => {
    render(<CoachSection />);
    expect(document.getElementById("coach")).toHaveAttribute("aria-labelledby", "coach-heading");
    expect(screen.getByText("Your personal AI mentor")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(
      "Meet Your AI IELTS Coach.",
    );
    expect(screen.getByText(/^Get personalized guidance, instant feedback/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Explore AI Coach (coming soon)" })).toHaveAttribute(
      "href",
      "/coach",
    );
  });

  it("the workspace is decorative, labelled as a sample, without controls or scores", () => {
    const { container } = render(<CoachSection />);
    const stage = container.querySelector("[data-decorative]");
    expect(stage).toHaveAttribute("aria-hidden", "true");
    expect(stage).toHaveAttribute("inert");
    expect(stage?.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    expect(stage?.querySelector(".cx-robot")).not.toBeNull();
    expect(stage?.querySelectorAll(".cx-rec")).toHaveLength(3);
    expect(stage).toHaveTextContent("Illustrative example, not a band score or an assessment.");
    expect(stage?.textContent).not.toMatch(/\b[4-9]\.[05]\b/);
  });

  it("plays the coaching sequence in order, then replays", async () => {
    vi.useFakeTimers();
    render(<CoachDemo />);
    expect(studentText()).toBe("");
    expect(mood()).toBe("idle");

    await until(() => studentText() === STUDENT_MESSAGE); // 3 · student message
    expect(mood()).toBe("listening");
    await until(typing); // the coach thinks
    expect(mood()).toBe("thinking");

    // 4 · the reply, word by word, while the coach talks.
    await until(() => coachText().split(" ").length >= 4);
    expect(mood()).toBe("talking");
    expect(COACH_MESSAGE.startsWith(coachText())).toBe(true);
    expect(coachText().length).toBeLessThan(COACH_MESSAGE.length);
    expect(feedbackShown()).toBe("false");

    // 5 · feedback, 6 · recommendations one by one, 7 · nod.
    await until(() => feedbackShown() === "true");
    expect(coachText()).toBe(COACH_MESSAGE);
    expect(recsShown()).toBe(0);
    await until(() => recsShown() === 1);
    await until(() => recsShown() === 3);
    await until(() => mood() === "done");

    // 8 · back to the start.
    await until(() => studentText() === "" && recsShown() === 0, 8000);
    expect(feedbackShown()).toBe("false");
  });

  it("shows the finished state without motion when reduced motion is requested", () => {
    mockReducedMotion(true);
    render(<CoachDemo />);
    expect(studentText()).toBe(STUDENT_MESSAGE);
    expect(coachText()).toBe(COACH_MESSAGE);
    expect(feedbackShown()).toBe("true");
    expect(recsShown()).toBe(3);
    expect(mood()).toBe("done");
  });

  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<CoachSection />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
