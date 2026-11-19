import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SiteShell } from "@/components/layout/site-shell";
import { Hero } from "@/components/marketing/hero";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
}));

const FOCUSABLE = "a, button, input, select, textarea, summary, [tabindex], [contenteditable]";
// Claims the landing page must never make without approved wording (product decision 2026-11-18).
const BANNED =
  /official partner|endorsed|approved by|british council|cambridge|idp|guarantee|trusted by|\d[\d,]*\+ (students|candidates|learners)|reviews/i;

beforeEach(() => {
  document.documentElement.lang = "en";
  document.title = "IELTS MASTER 2.0";
});

describe("Hero", () => {
  it("has one h1, real calls to action and passes axe as a full page", async () => {
    const { container } = renderWithProviders(
      <SiteShell layout="full">
        <Hero />
      </SiteShell>,
    );
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Prepare smarter.Achieve higher.",
    );
    const main = screen.getByRole("main");
    expect(screen.getAllByRole("link", { name: /start practising/i })[0]).toHaveAttribute(
      "href",
      "/practice",
    );
    expect(main.querySelector('a[href="/library"]')).toHaveTextContent("Browse the library");
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });

  it("product previews are decorative: hidden, inert and without focusable controls", () => {
    const { container } = render(<Hero />);
    const previews = container.querySelectorAll("[data-decorative]");
    expect(previews.length).toBeGreaterThan(0);
    for (const preview of previews) {
      expect(preview).toHaveAttribute("aria-hidden", "true");
      expect(preview).toHaveAttribute("inert");
      expect(preview.querySelectorAll(FOCUSABLE)).toHaveLength(0);
    }
    // The illustration is described once for screen-reader users.
    expect(screen.getByText(/Illustration of the practice interface/)).toHaveClass("sr-only");
  });

  it("makes no unapproved endorsement, affiliation or social-proof claims", () => {
    const { container } = render(<Hero />);
    expect(container.textContent).not.toMatch(BANNED);
  });
});

describe("TiltScene", () => {
  const original = window.matchMedia;

  function mockMedia(matches: (query: string) => boolean) {
    window.matchMedia = ((query: string) => ({
      matches: matches(query),
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;
  }

  function renderScene() {
    render(
      <section data-testid="area">
        <TiltScene className="hero-scene">
          <span>layer</span>
        </TiltScene>
      </section>,
    );
    const area = screen.getByTestId("area");
    area.getBoundingClientRect = () =>
      ({ left: 0, top: 0, width: 200, height: 100, right: 200, bottom: 100 }) as DOMRect;
    return { area, scene: screen.getByText("layer").parentElement as HTMLElement };
  }

  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", () => undefined);
  });
  afterEach(() => {
    window.matchMedia = original;
    vi.unstubAllGlobals();
  });

  it("tilts towards a fine pointer and resets on leave", () => {
    mockMedia((q) => q.includes("pointer: fine"));
    const { area, scene } = renderScene();
    fireEvent.pointerMove(area, { clientX: 200, clientY: 0 });
    expect(scene.style.getPropertyValue("--tilt-x")).toBe("1.000");
    expect(scene.style.getPropertyValue("--tilt-y")).toBe("-1.000");
    fireEvent.pointerLeave(area);
    expect(scene.style.getPropertyValue("--tilt-x")).toBe("0.000");
  });

  it("stays still when reduced motion is requested or the pointer is coarse", () => {
    mockMedia((q) => q.includes("reduce") || q.includes("pointer: fine"));
    const reduced = renderScene();
    fireEvent.pointerMove(reduced.area, { clientX: 200, clientY: 0 });
    expect(reduced.scene.style.getPropertyValue("--tilt-x")).toBe("");
  });

  it("stays still on touch devices", () => {
    mockMedia(() => false);
    const { area, scene } = renderScene();
    fireEvent.pointerMove(area, { clientX: 200, clientY: 0 });
    expect(scene.style.getPropertyValue("--tilt-x")).toBe("");
  });
});
