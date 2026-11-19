import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SiteShell } from "@/components/layout/site-shell";
import { FinalCtaSection, HowItWorksSection } from "@/components/marketing/closing-sections";
import { CoachSection } from "@/components/marketing/coach-section";
import { LibrarySection } from "@/components/marketing/library-section";
import { MockExamSection } from "@/components/marketing/mock-exam-section";
import { ProgressSection } from "@/components/marketing/progress-section";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

const FOCUSABLE = "a, button, input, select, textarea, summary, [tabindex], [contenteditable]";
const BANNED =
  /official partner|endorsed|approved by|british council|cambridge|\bidp\b|guarantee|trusted by|\d[\d,]*\+ (students|candidates|learners)|reviews|testimonial|★/i;
const PRICING = /\$|£\d|€|pricing|per month|\/ ?month|free trial|plans? from/i;

function Sections() {
  return (
    <>
      <CoachSection />
      <MockExamSection />
      <LibrarySection />
      <ProgressSection />
      <HowItWorksSection />
      <FinalCtaSection />
    </>
  );
}

beforeEach(() => {
  document.documentElement.lang = "en";
  document.title = "IELTS MASTER 2.0";
});

describe("Landing sections (L4)", () => {
  it("renders the six sections in order, each a labelled region with one h2", () => {
    render(<Sections />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Meet Your AI IELTS Coach.",
      "Experience the Real IELTS Exam Before Test Day.",
      "Everything You Need to Prepare, All in One Place.",
      "See Your Progress. Reach Your Target Band.",
      "Your IELTS Journey, Made Simpler.",
      "Your IELTS Goal Starts Here.",
    ]);
    for (const id of ["coach", "mock-exam", "library", "progress", "how-it-works"]) {
      expect(document.getElementById(id)).toHaveAttribute("aria-labelledby", `${id}-heading`);
    }
  });

  it("keeps previews decorative and describes each one once", () => {
    const { container } = render(<Sections />);
    const previews = container.querySelectorAll("[data-decorative]");
    expect(previews.length).toBe(5); // coach, mock exam, library, progress, final CTA emblem
    for (const preview of previews) {
      expect(preview).toHaveAttribute("aria-hidden", "true");
      expect(preview).toHaveAttribute("inert");
      expect(preview.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    }
    // The final CTA emblem is purely ornamental; the four product previews are described.
    expect(screen.getAllByText(/^Illustration: /)).toHaveLength(4);
  });

  it("links only to pages that work today, or are marked coming soon", () => {
    render(<Sections />);
    const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      "/coach",
      "/mock-tests",
      "/library",
      "/dashboard",
      "/register",
      "/practice",
    ]);
    // Everything except registration is a placeholder today, and says so.
    for (const name of [
      "Explore AI Coach (coming soon)",
      "Explore Mock Exams (coming soon)",
      "Explore Library (coming soon)",
      "Explore Your Dashboard (coming soon)",
      "Explore Practice (coming soon)",
    ]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Get Started" })).toHaveAttribute("href", "/register");
  });

  it("How it works is an ordered, four-step journey", () => {
    render(<HowItWorksSection />);
    const steps = screen.getAllByRole("listitem");
    expect(steps.map((li) => li.querySelector("h3")?.textContent)).toEqual([
      "Step 1: Create Your Account",
      "Step 2: Choose Your Practice",
      "Step 3: Learn with AI Guidance",
      "Step 4: Track Your Progress",
    ]);
  });

  it("labels sample data and estimates, and makes no unverifiable or pricing claims", () => {
    const { container } = render(<Sections />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED);
    expect(text).not.toMatch(PRICING);
    expect(screen.getByText(/Dashboard figures shown here are sample data/)).toBeVisible();
    expect(screen.getByText(/^The covers shown here are samples/)).toBeVisible();
  });

  it("passes axe as part of the full public page", async () => {
    const { container } = renderWithProviders(
      <SiteShell layout="full">
        <h1>Home</h1>
        <Sections />
      </SiteShell>,
    );
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });
});
