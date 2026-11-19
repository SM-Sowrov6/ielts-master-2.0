import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  inlineNodes,
  passageBody,
  wordCount,
} from "@/components/admin/listening/editor/passage-editor";
import { PassagePane } from "@/components/listening/passage-pane";

describe("reading passage helpers", () => {
  it("turns **bold** and _italic_ into marked text nodes", () => {
    expect(inlineNodes("a **b** _c_ d")).toEqual([
      { type: "text", text: "a " },
      { type: "text", text: "b", marks: [{ type: "bold" }] },
      { type: "text", text: " " },
      { type: "text", text: "c", marks: [{ type: "italic" }] },
      { type: "text", text: " d" },
    ]);
  });

  it("derives the body from non-empty paragraphs and counts words without markup", () => {
    const paragraphs = [
      { label: "A", text: "One **two** three." },
      { label: "B", text: "   " },
    ];
    expect(passageBody(paragraphs)).toMatchObject({
      type: "doc",
      content: [{ type: "paragraph" }],
    });
    expect(wordCount(paragraphs)).toBe(3);
  });
});

describe("PassagePane", () => {
  it("shows the title and labelled paragraphs, and an honest message without a passage", () => {
    const { rerender } = render(
      <PassagePane
        passages={[{ title: "Bees", body: {}, paragraphs: [{ label: "A", text: "Bees dance." }] }]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Bees" })).toBeInTheDocument();
    expect(screen.getByLabelText("Paragraph A")).toHaveTextContent("A");
    expect(screen.getByText("Bees dance.")).toBeInTheDocument();
    rerender(<PassagePane passages={[]} />);
    expect(screen.getByText(/passage for this part is not available/)).toBeInTheDocument();
  });
});
