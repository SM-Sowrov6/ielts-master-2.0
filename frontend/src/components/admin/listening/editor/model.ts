/**
 * Editor state <-> the import-format draft the API stores (SectionIn / GroupIn / QuestionIn).
 * Answers are authored in the existing key notation (QUESTION_BANK_DESIGN.md §5.2):
 * `(the) library` = optional word, `colour/color` = word alternatives, `a / b` = phrase
 * alternatives. The editor shows phrase alternatives as separate fields and joins them.
 */

import { QUESTION_TYPES } from "@/components/admin/listening/labels";
import type {
  AnswerDoc,
  Difficulty,
  EditorDocument,
  GroupDoc,
  OptionDoc,
  QuestionDoc,
  SaveDraftInput,
  SectionDoc,
} from "@/lib/admin/listening-api";
import { textToDoc } from "@/lib/admin/richtext";

export type DraftState = {
  title: string;
  description: string;
  difficulty: Difficulty | "";
  tags: string;
  minutes: string;
  adminNotes: string;
  changeNote: string;
  sections: SectionDoc[];
};

export function draftFromDocument(doc: EditorDocument): DraftState {
  const bySection = new Map(doc.sections.map((s) => [s.section_no, s]));
  return {
    title: doc.test.title,
    description: doc.version.description ?? "",
    difficulty: doc.version.difficulty ?? "",
    tags: doc.version.tags.join(", "),
    minutes: doc.duration_seconds ? String(Math.round(doc.duration_seconds / 60)) : "",
    adminNotes: doc.test.admin_notes ?? "",
    changeNote: doc.version.change_note ?? "",
    sections: [1, 2, 3, 4].map(
      (n) => bySection.get(n) ?? { section_no: n, groups: [], passages: [] },
    ),
  };
}

/** `revision` is the one the edits were based on (not necessarily the latest fetched). */
export function saveBody(
  doc: EditorDocument,
  draft: DraftState,
  revision: string = doc.version.revision,
): SaveDraftInput {
  const minutes = Number(draft.minutes);
  return {
    revision,
    title: draft.title.trim(),
    description: draft.description.trim() || null,
    difficulty: draft.difficulty || null,
    tags: [
      ...new Set(
        draft.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      ),
    ],
    duration_seconds: draft.minutes && Number.isFinite(minutes) ? Math.round(minutes * 60) : null,
    admin_notes: draft.adminNotes.trim() || null,
    change_note: draft.changeNote.trim() || null,
    sections: draft.sections,
  };
}

// ------------------------------------------------------------------------- numbering
export function questionNumbers(q: QuestionDoc): number[] {
  const to = q.number_to ?? q.number_from;
  const out: number[] = [];
  for (let n = q.number_from; n <= to; n++) out.push(n);
  return out;
}

export function allNumbers(sections: readonly SectionDoc[]): number[] {
  return sections.flatMap((s) =>
    (s.groups ?? []).flatMap((g) => g.questions.flatMap(questionNumbers)),
  );
}

export function nextNumber(sections: readonly SectionDoc[]): number {
  const used = allNumbers(sections);
  return Math.min(40, used.length ? Math.max(...used) + 1 : 1);
}

export function sectionRange(section: SectionDoc): string {
  const nums = (section.groups ?? []).flatMap((g) => g.questions.flatMap(questionNumbers));
  if (!nums.length) return "No questions";
  return `Questions ${Math.min(...nums)}–${Math.max(...nums)} (${nums.length})`;
}

// ------------------------------------------------------------------------- answers
const PHRASE_SPLIT = /\s+\/\s+/;

export function splitAlternatives(notation: string): string[] {
  return notation
    .split(PHRASE_SPLIT)
    .map((p) => p.trim())
    .filter(Boolean);
}

export function joinAlternatives(values: readonly string[]): string {
  return values
    .map((v) => v.trim())
    .filter(Boolean)
    .join(" / ");
}

export type AnswerMode = "text" | "numeric" | "time" | "date";

export function usesOptions(group: GroupDoc): boolean {
  const meta = QUESTION_TYPES[group.question_type];
  if (!meta) return false;
  if (meta.family !== "text") return true;
  return Boolean(meta.optionFormat) && group.config?.answer_format === "option";
}

/** Labels a question can be answered with (group options, then its own options). */
export function optionLabels(group: GroupDoc, question: QuestionDoc): string[] {
  const fixed = QUESTION_TYPES[group.question_type]?.fixedChoices;
  if (fixed) return [...fixed];
  return [...(group.options ?? []), ...(question.options ?? [])].map((o) => o.label);
}

export function optionAnswer(label: string): AnswerDoc[] {
  return label ? [{ value: label, slot: 1, match_mode: "option" }] : [];
}

export function multiAnswers(labels: readonly string[]): AnswerDoc[] {
  return labels.map((value, index) => ({ value, slot: index + 1, match_mode: "set_member" }));
}

export function textAnswer(alternatives: readonly string[], mode: AnswerMode): AnswerDoc[] {
  const value = joinAlternatives(alternatives);
  return value ? [{ value, slot: 1, match_mode: mode }] : [];
}

// ------------------------------------------------------------------------- factories
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function nextLabel(options: readonly OptionDoc[]): string {
  const used = new Set(options.map((o) => o.label));
  return [...LETTERS].find((l) => !used.has(l)) ?? String(options.length + 1);
}

export function newQuestion(type: string, number: number): QuestionDoc {
  const meta = QUESTION_TYPES[type];
  const isMulti = meta?.family === "multi_option";
  return {
    number_from: number,
    number_to: isMulti ? Math.min(40, number + 1) : null,
    stem: null,
    options: meta?.questionOptions
      ? [
          { label: "A", text: "" },
          { label: "B", text: "" },
          { label: "C", text: "" },
        ]
      : [],
    answers: [],
    explanation: null,
    config: {},
    tags: [],
  };
}

export function newGroup(type: string, number: number): GroupDoc {
  const meta = QUESTION_TYPES[type];
  return {
    question_type: type,
    instructions: meta?.defaultInstructions ?? null,
    config: meta?.family === "text" ? { word_limit: 2 } : {},
    image_asset_id: null,
    options: meta?.groupOptions
      ? [
          { label: "A", text: "" },
          { label: "B", text: "" },
          { label: "C", text: "" },
        ]
      : [],
    questions: [newQuestion(type, number)],
  };
}

/** Keep stems/explanations in the stored rich-text format. */
export function stemFromText(text: string): QuestionDoc["stem"] {
  return textToDoc(text);
}

export function explanationFromText(
  text: string,
  previous: QuestionDoc["explanation"],
): QuestionDoc["explanation"] {
  const body = textToDoc(text);
  const evidence = previous?.evidence_paragraph_label ?? null;
  if (!body && !evidence) return null;
  return {
    body: body ?? { type: "doc", content: [] },
    audio_start_ms: previous?.audio_start_ms ?? null,
    audio_end_ms: previous?.audio_end_ms ?? null,
    evidence_paragraph_label: evidence,
  };
}

/** Copy for "duplicate": a new question/group gets a new lineage (assigned by the server). */
export function cloneQuestion(q: QuestionDoc, number: number): QuestionDoc {
  const copy = structuredClone(q);
  delete copy.lineage_id;
  const span = (q.number_to ?? q.number_from) - q.number_from;
  copy.number_from = number;
  copy.number_to = span ? Math.min(40, number + span) : null;
  return copy;
}

export function cloneGroup(g: GroupDoc, firstNumber: number): GroupDoc {
  let n = firstNumber;
  return {
    ...structuredClone(g),
    questions: g.questions.map((q) => {
      const copy = cloneQuestion(q, n);
      n = (copy.number_to ?? copy.number_from) + 1;
      return copy;
    }),
  };
}

export function move<T>(items: readonly T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return [...items];
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item as T);
  return next;
}

/**
 * Questions are stored in number order, so moving a question means trading numbers with its
 * neighbour (each keeps its own span, e.g. a two-mark "Choose TWO").
 */
export function swapNumbers(
  questions: readonly QuestionDoc[],
  a: number,
  b: number,
): QuestionDoc[] {
  const first = questions[a];
  const second = questions[b];
  if (!first || !second) return [...questions];
  const lo = Math.min(first.number_from, second.number_from);
  const [earlier, later] = a < b ? [first, second] : [second, first];
  const laterSpan = (later.number_to ?? later.number_from) - later.number_from;
  const earlierSpan = (earlier.number_to ?? earlier.number_from) - earlier.number_from;
  const movedUp = { ...later, number_from: lo, number_to: laterSpan ? lo + laterSpan : null };
  const start = lo + laterSpan + 1;
  const movedDown = {
    ...earlier,
    number_from: start,
    number_to: earlierSpan ? start + earlierSpan : null,
  };
  const next = [...questions];
  next[Math.min(a, b)] = movedUp;
  next[Math.max(a, b)] = movedDown;
  return next;
}
