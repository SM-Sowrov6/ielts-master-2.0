import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SiteShell } from "@/components/layout/site-shell";
import { ModuleSections } from "@/components/marketing/modules";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

const FOCUSABLE = "a, button, input, select, textarea, summary, [tabindex], [contenteditable]";
const BANNED =
  /official partner|endorsed|approved by|british council|cambridge|\bidp\b|guarantee|trusted by|\d[\d,]*\+ (students|candidates|learners)|reviews|★/i;

beforeEach(() => {
  document.documentElement.lang = "en";
  document.title = "IELTS MASTER 2.0";
});

describe("ModuleSections (L3)", () => {
  it("renders four separate module sections in order with alternating layouts", () => {
    render(<ModuleSections />);
    const intro = screen.getByRole("heading", { level: 2, name: /Everything the IELTS test asks/ });
    expect(intro).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings).toHaveLength(4);
    const sections = ["listening", "reading", "writing", "speaking"].map((id) =>
      document.getElementById(id),
    );
    expect(sections.map((s) => s?.getAttribute("data-visual-side"))).toEqual([
      "right",
      "full", // Reading: introduction above a full-width display
      "full", // Writing: introduction above the full-width MacBook
      "full", // Speaking: introduction above the full-width speaking studio
    ]);
    expect(
      sections.map((s) => within(s as HTMLElement).getByText(/^Module \d\d · /).textContent),
    ).toEqual([
      "Module 01 · Listening",
      "Module 02 · Reading",
      "Module 03 · Writing",
      "Module 04 · Speaking",
    ]);
    for (const section of sections) {
      expect(section).toHaveAttribute("aria-labelledby", `${section?.id}-heading`);
    }
  });

  it("previews are decorative: hidden, inert, no controls, each described once", () => {
    const { container } = render(<ModuleSections />);
    const previews = container.querySelectorAll("[data-decorative]");
    expect(previews).toHaveLength(4);
    for (const preview of previews) {
      expect(preview).toHaveAttribute("aria-hidden", "true");
      expect(preview).toHaveAttribute("inert");
      expect(preview.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    }
    expect(screen.getAllByText(/^Illustration: /)).toHaveLength(3); // Writing has none, by request
  });

  it("never shows band figures in the sample previews (FR-WR-08)", () => {
    const { container } = render(<ModuleSections />);
    for (const preview of container.querySelectorAll("[data-decorative]")) {
      expect(preview.textContent).not.toMatch(/\b[4-9]\.[05]\b/);
    }
  });

  it("makes no affiliation, guarantee or social-proof claims", () => {
    const { container } = render(<ModuleSections />);
    expect(container.textContent).not.toMatch(BANNED);
  });

  it("passes axe inside the full public page", async () => {
    const { container } = renderWithProviders(
      <SiteShell layout="full">
        <h1>Home</h1>
        <ModuleSections />
      </SiteShell>,
    );
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });
});
