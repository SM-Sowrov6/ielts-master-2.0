"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, EyeIcon, EyeOffIcon, InfoIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { MediaField } from "@/components/admin/listening/editor/media-field";
import {
  DIFFICULTY_LABELS,
  StatusBadge,
  formatDuration,
  typeLabel,
} from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import {
  fetchEditorDocument,
  fetchPreview,
  type Asset,
  type Difficulty,
} from "@/lib/admin/listening-api";
import { docToText } from "@/lib/admin/richtext";
import { PassagePane } from "@/components/listening/passage-pane";
import { messageFor } from "@/lib/auth/api";
import type { Passage } from "@/lib/exam/api";
import { useModuleInfo } from "@/lib/admin/module";
import { queryKeys } from "@/lib/query/keys";
import { cn } from "@/lib/utils";

type Option = { label: string; text: string };
type PreviewQuestion = {
  number_from: number;
  number_to: number;
  marks: number;
  stem: unknown;
  options?: Option[];
};
type PreviewAnswer = {
  number_from: number;
  number_to: number;
  accepted: string[][];
  explanation: unknown;
};
type PreviewGroup = {
  question_type: string;
  instructions: string | null;
  answer_format: string;
  config: Record<string, unknown>;
  options: Option[];
  questions: PreviewQuestion[];
  image_asset_id: string | null;
  answers: PreviewAnswer[];
};
type PreviewSection = {
  section_no: number;
  title: string | null;
  instructions: string | null;
  context: string | null;
  audio_asset_id: string | null;
  passages?: Passage[];
  groups: PreviewGroup[];
};

function OptionList({ options }: { options: Option[] }) {
  if (!options.length) return null;
  return (
    <ul className="grid gap-1 text-sm sm:grid-cols-2">
      {options.map((o) => (
        <li key={o.label} className="flex gap-2">
          <span className="font-semibold">{o.label}</span>
          <span>{o.text}</span>
        </li>
      ))}
    </ul>
  );
}

function Group({
  group,
  showAnswers,
  assets,
  testId,
}: {
  group: PreviewGroup;
  showAnswers: boolean;
  assets: ReadonlyMap<string, Asset>;
  testId: string;
}) {
  const numbers = group.questions.flatMap((q) => [q.number_from, q.number_to]);
  const answerFor = (q: PreviewQuestion) =>
    group.answers.find((a) => a.number_from === q.number_from);
  const text = group.answer_format === "text";
  return (
    <section
      className="space-y-3 rounded-xl border bg-card p-4"
      aria-label={`Questions ${Math.min(...numbers)}–${Math.max(...numbers)}`}
    >
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Questions {Math.min(...numbers)}–{Math.max(...numbers)} · {typeLabel(group.question_type)}
      </p>
      {group.instructions && <p className="text-sm font-medium">{group.instructions}</p>}
      {group.image_asset_id && (
        <MediaField
          label="Image"
          kind="image"
          testId={testId}
          assetId={group.image_asset_id}
          assets={assets}
          readOnly
          onUploaded={() => undefined}
        />
      )}
      <OptionList options={group.options} />
      <ol className="space-y-3">
        {group.questions.map((q) => {
          const answer = answerFor(q);
          return (
            <li key={q.number_from} className="space-y-2">
              <div className="flex gap-3">
                <span className="grid size-7 shrink-0 place-items-center rounded-md border text-xs font-semibold tabular-nums">
                  {q.number_from === q.number_to
                    ? q.number_from
                    : `${q.number_from}–${q.number_to}`}
                </span>
                <div className="min-w-0 flex-1 space-y-2">
                  {Boolean(q.stem) && (
                    <p className="text-sm whitespace-pre-line">{docToText(q.stem)}</p>
                  )}
                  {q.options && <OptionList options={q.options} />}
                  {text ? (
                    <div
                      aria-hidden="true"
                      className="h-8 max-w-xs rounded-md border border-dashed bg-muted/40"
                    />
                  ) : null}
                </div>
              </div>
              {showAnswers && answer && (
                <div className="ml-10 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm">
                  <p>
                    <span className="font-medium">Answer: </span>
                    {answer.accepted.map((alts) => alts.join(" | ")).join(" + ")}
                  </p>
                  {Boolean(answer.explanation) && (
                    <p className="text-muted-foreground whitespace-pre-line">
                      {docToText(answer.explanation)}
                    </p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Admin-only preview. Not a candidate attempt: nothing is answered, scored or stored. */
export function ListeningPreview({ versionId }: { versionId: string }) {
  const { base, module } = useModuleInfo();
  const sectionNoun = module === "reading" ? "Passage" : "Part";
  const preview = useQuery({
    queryKey: queryKeys.listening.preview(versionId),
    queryFn: () => fetchPreview(versionId),
  });
  const doc = useQuery({
    queryKey: queryKeys.listening.document(versionId),
    queryFn: () => fetchEditorDocument(versionId),
  });
  const [showAnswers, setShowAnswers] = useState(false);
  const [active, setActive] = useState(1);

  if (preview.isPending || doc.isPending) return <LoadingState label="Loading preview…" />;
  if (preview.isError || doc.isError)
    return (
      <ErrorState
        title="The preview could not be loaded"
        description={messageFor(preview.error ?? doc.error)}
      />
    );

  const p = preview.data;
  const sections = p.sections as unknown as PreviewSection[];
  const assets = new Map(doc.data.assets.map((a) => [a.id, a]));
  const section = sections.find((s) => s.section_no === active) ?? sections[0];
  const status = doc.data.version.approved ? "approved" : doc.data.version.status;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link href={`${base}/${versionId}`}>
            <ArrowLeftIcon aria-hidden="true" />
            Back to editor
          </Link>
        </Button>
        <Button
          variant={showAnswers ? "default" : "outline"}
          size="sm"
          aria-pressed={showAnswers}
          onClick={() => setShowAnswers((v) => !v)}
        >
          {showAnswers ? <EyeOffIcon aria-hidden="true" /> : <EyeIcon aria-hidden="true" />}
          {showAnswers ? "Hide answers" : "Show answers"}
        </Button>
      </div>
      <p className="flex items-start gap-2 rounded-lg border border-info/40 bg-info/5 px-4 py-3 text-sm">
        <InfoIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        Admin preview of how candidates will see this test. It is not an attempt: nothing is
        answered, scored or saved. Answers are visible to staff only.
      </p>
      <header className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">{p.title}</h1>
          <StatusBadge status={status} />
        </div>
        <p className="text-sm text-muted-foreground">
          {p.code} · version {p.version_no} · {formatDuration(p.duration_seconds)}
          {p.difficulty && ` · ${DIFFICULTY_LABELS[p.difficulty as Difficulty]}`}
        </p>
        {p.description && <p className="max-w-[var(--container-prose)] text-sm">{p.description}</p>}
      </header>
      <nav aria-label="Test sections">
        <ul className="flex flex-wrap gap-2">
          {sections.map((s) => (
            <li key={s.section_no}>
              <button
                type="button"
                onClick={() => setActive(s.section_no)}
                aria-current={s.section_no === active ? "step" : undefined}
                className={cn(
                  "rounded-full border px-4 py-1.5 text-sm font-medium hover:bg-muted",
                  s.section_no === active &&
                    "border-primary bg-primary text-primary-foreground hover:bg-primary",
                )}
              >
                {sectionNoun} {s.section_no}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      {section && (
        <div className="space-y-4">
          <div className="space-y-1">
            <h2 className="font-heading text-lg font-semibold">
              {sectionNoun} {section.section_no}
              {section.title ? `: ${section.title}` : ""}
            </h2>
            {section.context && <p className="text-sm text-muted-foreground">{section.context}</p>}
            {section.instructions && <p className="text-sm">{section.instructions}</p>}
          </div>
          {module === "reading" ? (
            <PassagePane passages={section.passages ?? []} />
          ) : section.audio_asset_id ? (
            <MediaField
              label="Recording"
              kind="audio"
              testId={p.test_id}
              assetId={section.audio_asset_id}
              assets={assets}
              readOnly
              onUploaded={() => undefined}
            />
          ) : (
            <p className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
              No audio uploaded for this part yet.
            </p>
          )}
          {section.groups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No questions in this part yet.</p>
          ) : (
            section.groups.map((g, i) => (
              <Group
                key={i}
                group={g}
                showAnswers={showAnswers}
                assets={assets}
                testId={p.test_id}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
