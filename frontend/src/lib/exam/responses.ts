/** Helpers shared by the candidate renderers, the review screen and the navigation panel. */

import type { ContentGroup, ContentSection, Response } from "@/lib/exam/api";

export function isAnswered(response: Response | undefined): boolean {
  if (!response) return false;
  if ("text" in response) return response.text.trim().length > 0;
  if ("choice" in response) return response.choice.length > 0;
  return response.choices.length > 0;
}

/** Display form of a candidate response (labels for choices, text as typed). */
export function formatResponse(response: Response | undefined | null): string {
  if (!response) return "—";
  if ("text" in response) return response.text.trim() || "—";
  if ("choice" in response) return response.choice;
  return response.choices.length ? response.choices.join(", ") : "—";
}

/** Word count consistent with the IELTS "words and/or a number" hint shown to candidates. */
export function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export type QuestionRef = {
  id: string;
  label: string; // "12" or "17–18"
  numbers: number[];
  sectionNo: number;
};

export function questionRefs(sections: readonly ContentSection[]): QuestionRef[] {
  return sections.flatMap((s) =>
    s.groups.flatMap((g: ContentGroup) =>
      g.questions.map((q) => {
        const numbers: number[] = [];
        for (let n = q.number_from; n <= q.number_to; n++) numbers.push(n);
        return {
          id: q.id,
          label:
            q.number_from === q.number_to ? `${q.number_from}` : `${q.number_from}–${q.number_to}`,
          numbers,
          sectionNo: s.section_no,
        };
      }),
    ),
  );
}

/** Remaining milliseconds from a server deadline, using the server-clock offset. */
export function remainingMs(deadlineIso: string, offsetMs: number, now = Date.now()): number {
  return Date.parse(deadlineIso) - (now + offsetMs);
}

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
