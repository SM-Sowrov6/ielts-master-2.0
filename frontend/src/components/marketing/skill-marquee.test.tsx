import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { REPEATS_PER_COPY, SkillMarquee, STRIPS } from "@/components/marketing/skill-marquee";
import { axeViolations } from "@/test/axe";

beforeEach(() => {
  document.documentElement.lang = "en";
});

describe("SkillMarquee", () => {
  it("renders two strips with opposite directions and distinct speeds", () => {
    const { container } = render(<SkillMarquee />);
    const strips = [...container.querySelectorAll<HTMLElement>(".marquee")];
    expect(strips.map((s) => s.dataset.direction)).toEqual(["ltr", "rtl"]);
    const speeds = strips.map((s) => s.style.getPropertyValue("--marquee-duration"));
    expect(new Set(speeds).size).toBe(2);
  });

  it("builds each track from two identical copies for a seamless loop", () => {
    const { container } = render(<SkillMarquee />);
    for (const [index, track] of [...container.querySelectorAll(".marquee-track")].entries()) {
      const copies = track.querySelectorAll(":scope > ul");
      expect(copies).toHaveLength(2);
      expect(copies[0]?.textContent).toBe(copies[1]?.textContent);
      const labels = STRIPS[index]?.items.map((i) => i.label).join("") ?? "";
      expect(copies[0]?.textContent).toBe(labels.repeat(REPEATS_PER_COPY));
    }
  });

  it("every item has a layered 3D icon (extrusion, face, glyph, shadow)", () => {
    const { container } = render(<SkillMarquee />);
    const icons = container.querySelectorAll(".icon3d");
    expect(icons.length).toBe(2 * 2 * 5 * REPEATS_PER_COPY);
    for (const icon of icons) {
      expect(icon.querySelectorAll(".icon3d-depth")).toHaveLength(5);
      expect(icon.querySelector(".icon3d-face")).not.toBeNull();
      expect(icon.querySelector(".icon3d-glyph svg")).not.toBeNull();
      expect(icon.querySelector(".icon3d-shadow")).not.toBeNull();
    }
  });

  it("hides the moving copies from assistive technology and lists each topic once", () => {
    render(<SkillMarquee />);
    const region = screen.getByRole("region", { name: "What IELTS MASTER covers" });
    const list = within(region).getByRole("list");
    const topics = within(list)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(topics).toHaveLength(10);
    expect(topics).toContain("Band Score");
    expect(region.querySelector(".marquee")?.closest("[aria-hidden='true']")).not.toBeNull();
  });

  it("passes axe", { timeout: 30_000 }, async () => {
    const { container } = render(<SkillMarquee />);
    expect(await axeViolations(container)).toEqual([]);
  });
});
