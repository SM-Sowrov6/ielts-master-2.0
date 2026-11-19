import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { axeViolations } from "@/test/axe";

// Guards against a vacuous helper: it must report real violations.
describe("axeViolations", () => {
  it("reports an unlabelled form control and an image without alt text", async () => {
    const { container } = render(
      <div>
        <input type="text" />
        {/* Deliberately inaccessible markup: this test proves the axe helper detects it. */}
        {/* eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text */}
        <img src="/x.png" />
      </div>,
    );
    const violations = await axeViolations(container);
    expect(violations.some((v) => v.startsWith("label:"))).toBe(true);
    expect(violations.some((v) => v.startsWith("image-alt:"))).toBe(true);
  });

  it("reports content outside landmarks when checking a full page", async () => {
    const { container } = render(<p>Orphan content</p>);
    expect(
      (await axeViolations(container, { page: true })).some((v) => v.startsWith("region:")),
    ).toBe(true);
  });
});
