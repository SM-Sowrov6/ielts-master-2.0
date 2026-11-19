import { Badge } from "@/components/ui/badge";
import type { Difficulty, ListStatus } from "@/lib/admin/listening-api";
import { cn } from "@/lib/utils";

export const STATUS_LABELS: Record<ListStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  published: "Published",
  archived: "Archived",
};

const STATUS_STYLES: Record<ListStatus, string> = {
  draft: "border-border bg-muted text-foreground",
  in_review: "border-warning/40 bg-warning/10 text-foreground",
  approved: "border-info/40 bg-info/10 text-foreground",
  published: "border-success/40 bg-success/10 text-success",
  archived: "border-border bg-background text-muted-foreground",
};

export function StatusBadge({ status }: { status: ListStatus }) {
  return (
    <Badge variant="outline" className={cn("font-medium", STATUS_STYLES[status])}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}

/** Existing content difficulty values, shown with the labels the admin team uses. */
export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  easy: "Beginner",
  medium: "Intermediate",
  hard: "Advanced",
};

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const minutes = Math.round(seconds / 60);
  return `${minutes} min`;
}

const dateTime = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function formatDate(iso: string): string {
  return `${dateTime.format(new Date(iso))} UTC`;
}

/**
 * Editor metadata for the canonical Listening question types (codes from the backend registry;
 * never renamed here). `answer` decides the key editor; `groupOptions` / `questionOptions`
 * decide where the choice list lives; `optionFormat` marks types that may use a word bank.
 */
export type TypeMeta = {
  label: string;
  family: "option" | "multi_option" | "text";
  groupOptions?: boolean;
  questionOptions?: boolean;
  optionFormat?: boolean;
  image?: boolean;
  /** Server-fixed choices (TRUE/FALSE/NOT GIVEN): no option editor. */
  fixedChoices?: readonly string[];
  defaultInstructions: string;
};

export const QUESTION_TYPES: Record<string, TypeMeta> = {
  mcq_single: {
    label: "Multiple choice (one answer)",
    family: "option",
    questionOptions: true,
    defaultInstructions: "Choose the correct letter, A, B or C.",
  },
  mcq_multi: {
    label: "Multiple choice (more than one answer)",
    family: "multi_option",
    groupOptions: true,
    defaultInstructions: "Choose TWO letters, A–E.",
  },
  matching_features: {
    label: "Matching",
    family: "option",
    groupOptions: true,
    defaultInstructions: "Choose your answers from the box and write the correct letter.",
  },
  form_completion: {
    label: "Form completion",
    family: "text",
    defaultInstructions: "Write NO MORE THAN TWO WORDS AND/OR A NUMBER for each answer.",
  },
  note_completion: {
    label: "Note completion",
    family: "text",
    defaultInstructions: "Write ONE WORD ONLY for each answer.",
  },
  table_completion: {
    label: "Table completion",
    family: "text",
    defaultInstructions: "Write NO MORE THAN TWO WORDS for each answer.",
  },
  flowchart_completion: {
    label: "Flow-chart completion",
    family: "text",
    optionFormat: true,
    defaultInstructions: "Write ONE WORD ONLY for each answer.",
  },
  summary_completion: {
    label: "Summary completion",
    family: "text",
    optionFormat: true,
    defaultInstructions: "Write ONE WORD ONLY for each answer.",
  },
  sentence_completion: {
    label: "Sentence completion",
    family: "text",
    defaultInstructions: "Write ONE WORD ONLY for each answer.",
  },
  short_answer: {
    label: "Short answer",
    family: "text",
    defaultInstructions: "Write NO MORE THAN THREE WORDS for each answer.",
  },
  map_labelling: {
    label: "Map labelling",
    family: "option",
    groupOptions: true,
    image: true,
    defaultInstructions: "Label the map. Write the correct letter next to each question.",
  },
  plan_labelling: {
    label: "Plan labelling",
    family: "text",
    optionFormat: true,
    image: true,
    defaultInstructions: "Label the plan. Write ONE WORD ONLY for each answer.",
  },
  diagram_labelling: {
    label: "Diagram labelling",
    family: "text",
    optionFormat: true,
    image: true,
    defaultInstructions: "Label the diagram. Write ONE WORD ONLY for each answer.",
  },
  tfng: {
    label: "True / False / Not Given",
    family: "option",
    fixedChoices: ["TRUE", "FALSE", "NOT GIVEN"],
    defaultInstructions:
      "Do the following statements agree with the information given in the passage? Write TRUE, FALSE or NOT GIVEN.",
  },
  ynng: {
    label: "Yes / No / Not Given",
    family: "option",
    fixedChoices: ["YES", "NO", "NOT GIVEN"],
    defaultInstructions:
      "Do the following statements agree with the claims of the writer? Write YES, NO or NOT GIVEN.",
  },
  matching_headings: {
    label: "Matching headings",
    family: "option",
    groupOptions: true,
    defaultInstructions: "Choose the correct heading for each paragraph from the list of headings.",
  },
  matching_information: {
    label: "Matching information",
    family: "option",
    groupOptions: true,
    defaultInstructions:
      "Which paragraph contains the following information? Write the correct letter.",
  },
  matching_sentence_endings: {
    label: "Matching sentence endings",
    family: "option",
    groupOptions: true,
    defaultInstructions: "Complete each sentence with the correct ending from the box.",
  },
};

export function typeLabel(code: string): string {
  return QUESTION_TYPES[code]?.label ?? code;
}

export const SECTION_KINDS: Record<number, string> = {
  1: "Everyday social conversation",
  2: "Everyday social monologue",
  3: "Educational or training conversation",
  4: "Academic monologue",
};
