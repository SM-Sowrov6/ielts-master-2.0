"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";
import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { components } from "@/lib/api/schema";

type Passage = components["schemas"]["PassageIn"];
type Paragraph = components["schemas"]["ParagraphIn"];

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

/** `**bold**` and `_italic_` → ProseMirror text nodes with marks (the stored rich-text format). */
export function inlineNodes(text: string): Record<string, unknown>[] {
  const nodes: Record<string, unknown>[] = [];
  const re = /\*\*(.+?)\*\*|_(.+?)_/g;
  let last = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) nodes.push({ type: "text", text: text.slice(last, m.index) });
    nodes.push({
      type: "text",
      text: m[1] ?? m[2],
      marks: [{ type: m[1] ? "bold" : "italic" }],
    });
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push({ type: "text", text: text.slice(last) });
  return nodes;
}

/** The passage body is derived from its paragraphs so the two can never disagree. */
export function passageBody(paragraphs: readonly Paragraph[]): Passage["body"] {
  return {
    type: "doc",
    content: paragraphs
      .filter((p) => p.text.trim())
      .map((p) => ({ type: "paragraph", content: inlineNodes(p.text) })),
  };
}

export function wordCount(paragraphs: readonly Paragraph[]): number {
  return paragraphs.reduce(
    (n, p) =>
      n +
      p.text
        .replace(/\*\*|_/g, "")
        .split(/\s+/)
        .filter(Boolean).length,
    0,
  );
}

export function PassageEditor({
  passage,
  readOnly,
  onChange,
}: {
  passage: Passage | undefined;
  readOnly: boolean;
  onChange: (p: Passage) => void;
}) {
  const id = useId();
  const paragraphs = passage?.paragraphs ?? [];
  const set = (next: Paragraph[], title = passage?.title ?? null) =>
    onChange({ title, paragraphs: next, body: passageBody(next) });
  const words = wordCount(paragraphs);

  return (
    <section aria-labelledby={`${id}-h`} className="space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`${id}-h`} className="font-heading text-base font-semibold">
          Reading passage
        </h3>
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {words} words · {paragraphs.length} paragraphs
          {words > 0 &&
            (words < 700 || words > 1000) &&
            " · IELTS passages are usually 700–1,000 words"}
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-title`}>Passage title</Label>
        <Input
          id={`${id}-title`}
          value={passage?.title ?? ""}
          readOnly={readOnly}
          maxLength={300}
          onChange={(e) => set(paragraphs, e.target.value || null)}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Label paragraphs (A, B, …) when questions refer to them. Use **bold** or _italic_ for
        emphasis.
      </p>
      <ol className="space-y-3">
        {paragraphs.map((p, i) => (
          <li key={i} className="flex gap-2">
            <Input
              aria-label={`Paragraph ${i + 1} label`}
              className="w-14 shrink-0 text-center"
              value={p.label ?? ""}
              readOnly={readOnly}
              maxLength={4}
              onChange={(e) =>
                set(
                  paragraphs.map((x, j) => (j === i ? { ...x, label: e.target.value || null } : x)),
                )
              }
            />
            <Textarea
              aria-label={`Paragraph ${i + 1} text`}
              rows={4}
              value={p.text}
              readOnly={readOnly}
              onChange={(e) =>
                set(paragraphs.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
              }
            />
            {!readOnly && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove paragraph ${i + 1}`}
                onClick={() => set(paragraphs.filter((_, j) => j !== i))}
              >
                <Trash2Icon aria-hidden="true" />
              </Button>
            )}
          </li>
        ))}
      </ol>
      {!readOnly && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            set([...paragraphs, { label: LETTERS[paragraphs.length] ?? null, text: "" }])
          }
        >
          <PlusIcon aria-hidden="true" />
          Add paragraph
        </Button>
      )}
    </section>
  );
}
