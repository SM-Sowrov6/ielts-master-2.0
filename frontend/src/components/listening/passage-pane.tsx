"use client";

import type { Passage } from "@/lib/exam/api";

/**
 * Reading passage beside the questions. Paragraph labels (A, B, …) are shown because
 * matching-information/headings questions refer to them. Scrolls independently on wide screens.
 */
export function PassagePane({
  passages,
  embedded = false,
}: {
  passages: Passage[];
  /** Inside a scrolling split pane: no sticky positioning or own scroll area. */
  embedded?: boolean;
}) {
  if (!passages.length) {
    return (
      <p className="rounded-lg border bg-card p-4 text-sm text-destructive">
        The passage for this part is not available.
      </p>
    );
  }
  return (
    <article
      aria-label="Reading passage"
      className={
        embedded
          ? "space-y-6 rounded-xl border bg-card p-6 text-[1.0625rem] leading-8"
          : "space-y-6 rounded-xl border bg-card p-5 leading-relaxed lg:sticky lg:top-20 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto"
      }
    >
      {passages.map((p, i) => (
        <section key={i} className="space-y-3">
          {p.title && <h2 className="font-heading text-xl font-semibold">{p.title}</h2>}
          {p.paragraphs.map((para, j) => (
            <p key={j} className="flex gap-3">
              {para.label && (
                <span className="font-semibold text-primary" aria-label={`Paragraph ${para.label}`}>
                  {para.label}
                </span>
              )}
              <span className="whitespace-pre-line">{para.text}</span>
            </p>
          ))}
        </section>
      ))}
    </article>
  );
}
