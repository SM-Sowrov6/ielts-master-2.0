import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SplitPane } from "@/components/listening/split-pane";

describe("SplitPane", () => {
  it("resizes the passage pane with the keyboard within bounds and resets on double-click", () => {
    localStorage.clear();
    render(<SplitPane left={<p>Passage</p>} right={<p>Questions</p>} />);
    const divider = screen.getByRole("separator", { name: "Resize passage and questions" });
    expect(divider).toHaveAttribute("aria-valuenow", "50");
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    expect(divider).toHaveAttribute("aria-valuenow", "55");
    fireEvent.keyDown(divider, { key: "End" });
    expect(divider).toHaveAttribute("aria-valuenow", "75");
    fireEvent.keyDown(divider, { key: "ArrowRight" });
    expect(divider).toHaveAttribute("aria-valuenow", "75");
    expect(localStorage.getItem("reading-split")).toBe("75");
    fireEvent.doubleClick(divider);
    expect(divider).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByText("Passage")).toBeInTheDocument();
    expect(screen.getByText("Questions")).toBeInTheDocument();
  });
});
