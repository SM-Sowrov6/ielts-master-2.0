"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, CheckIcon, InfoIcon, MinusIcon, RotateCcwIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { typeLabel } from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { docToText } from "@/lib/admin/richtext";
import { messageFor } from "@/lib/auth/api";
import { useExamModule } from "@/lib/exam/module";
import {
  fetchAttempt,
  fetchResult,
  fetchReview,
  type ContentSection,
  type ReviewItem,
} from "@/lib/exam/api";
import { formatResponse } from "@/lib/exam/responses";
import { cn } from "@/lib/utils";

const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max ? Math.round((value / max) * 100) : 0;
  return (
    <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden="true">
      <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
    </div>
  );
}

function ReviewRow({
  item,
  stem,
  options,
}: {
  item: ReviewItem;
  stem: unknown;
  options: Map<string, string>;
}) {
  const label =
    item.number_from === item.number_to
      ? `${item.number_from}`
      : `${item.number_from}–${item.number_to}`;
  const unanswered = item.reason === "no_response";
  const status = item.is_correct
    ? "Correct"
    : unanswered
      ? "Not answered"
      : item.marks_awarded > 0
        ? "Partly correct"
        : "Incorrect";
  const Icon = item.is_correct ? CheckIcon : unanswered ? MinusIcon : XIcon;
  const accepted = item.accepted.map((alts) =>
    alts.map((a) => (options.has(a) ? `${a} (${options.get(a)})` : a)),
  );
  return (
    <li
      className={cn(
        "space-y-2 rounded-xl border p-4",
        item.is_correct ? "border-success/30" : unanswered ? "" : "border-destructive/30",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "grid size-8 shrink-0 place-items-center rounded-md text-sm font-semibold tabular-nums",
            item.is_correct
              ? "bg-success/10 text-success"
              : unanswered
                ? "bg-muted"
                : "bg-destructive/10 text-destructive",
          )}
        >
          {label}
        </span>
        <div className="min-w-0 flex-1 space-y-2 text-sm">
          {docToText(stem) && <p className="whitespace-pre-line">{docToText(stem)}</p>}
          <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Your answer</dt>
              <dd className="font-medium">{formatResponse(item.response as never)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Correct answer</dt>
              <dd className="font-medium">
                {accepted.map((alts) => alts.join(" / ")).join(" + ")}
              </dd>
            </div>
          </dl>
          {item.evidence_paragraph && (
            <p className="text-xs text-muted-foreground">
              Evidence: paragraph {item.evidence_paragraph}
            </p>
          )}
          {item.explanation && (
            <p className="rounded-md bg-muted/60 px-3 py-2 text-muted-foreground whitespace-pre-line">
              {docToText(item.explanation)}
            </p>
          )}
        </div>
        <span
          className={cn(
            "flex shrink-0 items-center gap-1 text-xs font-medium",
            item.is_correct
              ? "text-success"
              : unanswered
                ? "text-muted-foreground"
                : "text-destructive",
          )}
        >
          <Icon className="size-4" aria-hidden="true" />
          {status}
          <span className="sr-only">
            , {item.marks_awarded} of {item.marks} marks
          </span>
        </span>
      </div>
    </li>
  );
}

export function AttemptResult({ attemptId }: { attemptId: string }) {
  const { title, base, examBase, partNoun } = useExamModule();
  const attempt = useQuery({
    queryKey: ["attempt", attemptId],
    queryFn: () => fetchAttempt(attemptId),
  });
  const done = attempt.data?.status === "completed";
  const result = useQuery({
    queryKey: ["attempt-result", attemptId],
    queryFn: () => fetchResult(attemptId),
    enabled: done,
  });
  const review = useQuery({
    queryKey: ["attempt-review", attemptId],
    queryFn: () => fetchReview(attemptId),
    enabled: done,
  });
  const [filter, setFilter] = useState<"all" | "wrong">("all");

  if (attempt.isPending || (done && (result.isPending || review.isPending)))
    return <LoadingState label="Loading your result…" />;
  if (attempt.isError || result.isError || review.isError) {
    return (
      <ErrorState
        title="The result could not be loaded"
        description={messageFor(attempt.error ?? result.error ?? review.error)}
        action={
          <Button asChild variant="outline">
            <Link href={base}>Back to {title}</Link>
          </Button>
        }
      />
    );
  }
  if (!done) {
    return (
      <ErrorState
        icon={InfoIcon}
        title="This attempt has not been submitted"
        description="Results and answers are shown after you submit."
        action={
          <Button asChild>
            <Link href={`${examBase}/${attemptId}`}>Continue the test</Link>
          </Button>
        }
      />
    );
  }
  const r = result.data!;
  const rv = review.data!;
  const sections = (rv.content as { sections: ContentSection[] }).sections;
  const stems = new Map<string, unknown>();
  const options = new Map<string, Map<string, string>>();
  for (const s of sections)
    for (const g of s.groups)
      for (const q of g.questions) {
        stems.set(q.id, q.stem);
        options.set(
          q.id,
          new Map([...(g.options ?? []), ...(q.options ?? [])].map((o) => [o.label, o.text])),
        );
      }
  const items = rv.items.filter((i) => filter === "all" || !i.is_correct);

  return (
    <div className="space-y-8">
      <Button asChild variant="ghost" size="sm">
        <Link href={base}>
          <ArrowLeftIcon aria-hidden="true" />
          {title}
        </Link>
      </Button>
      <section
        aria-labelledby="result"
        className="rounded-2xl border bg-card p-6 shadow-elevation-1 sm:p-8"
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              {r.attempt.mode === "exam" ? "Exam mode" : "Practice"} · submitted{" "}
              {r.attempt.completed_at ? dateTime.format(new Date(r.attempt.completed_at)) : ""}
              {r.attempt.submitted_by === "deadline" && " · time ran out"}
            </p>
            <h1
              id="result"
              className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl"
            >
              {r.attempt.test.title}
            </h1>
          </div>
          <div className="flex items-end gap-6">
            <div>
              <p className="text-xs text-muted-foreground">Score</p>
              <p className="font-heading text-4xl font-semibold tabular-nums">
                {r.raw_score}
                <span className="text-xl text-muted-foreground">/{r.max_score}</span>
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Accuracy</p>
              <p className="font-heading text-4xl font-semibold tabular-nums">{r.percentage}%</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Band estimate</p>
              {r.band_available ? (
                <p className="font-heading text-4xl font-semibold tabular-nums">
                  {r.band_estimate}
                </p>
              ) : (
                <p className="max-w-[12rem] text-sm text-muted-foreground">
                  Not available yet: no approved score-to-band table.
                </p>
              )}
            </div>
          </div>
        </div>
        <dl className="mt-6 grid grid-cols-3 gap-3 text-center text-sm">
          <div className="rounded-lg bg-success/10 py-2">
            <dt className="text-xs text-muted-foreground">Correct</dt>
            <dd className="font-semibold">{r.correct}</dd>
          </div>
          <div className="rounded-lg bg-destructive/10 py-2">
            <dt className="text-xs text-muted-foreground">Incorrect</dt>
            <dd className="font-semibold">{r.incorrect}</dd>
          </div>
          <div className="rounded-lg bg-muted py-2">
            <dt className="text-xs text-muted-foreground">Not answered</dt>
            <dd className="font-semibold">{r.unanswered}</dd>
          </div>
        </dl>
        {r.band_available && (
          <p className="mt-3 text-xs text-muted-foreground">
            Band estimates are approximations, not official IELTS results.
          </p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="by-part" className="space-y-3 rounded-2xl border bg-card p-5">
          <h2 id="by-part" className="font-heading text-lg font-semibold">
            By part
          </h2>
          <ul className="space-y-3">
            {r.sections.map((s) => (
              <li key={s.section_no} className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span>
                    {partNoun} {s.section_no}
                  </span>
                  <span className="tabular-nums">
                    {s.marks}/{s.max}
                  </span>
                </div>
                <Bar value={s.marks} max={s.max} />
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="by-type" className="space-y-3 rounded-2xl border bg-card p-5">
          <h2 id="by-type" className="font-heading text-lg font-semibold">
            By question type
          </h2>
          <ul className="space-y-3">
            {r.question_types.map((t) => (
              <li key={t.question_type} className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span>{typeLabel(t.question_type)}</span>
                  <span className="tabular-nums">
                    {t.marks}/{t.max}
                  </span>
                </div>
                <Bar value={t.marks} max={t.max} />
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section aria-labelledby="answers" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="answers" className="font-heading text-lg font-semibold">
            Answer review
          </h2>
          <div className="flex gap-1 rounded-lg border p-1">
            {(["all", "wrong"] as const).map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={cn(
                  "rounded-md px-3 py-1 text-xs font-medium",
                  filter === f ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
              >
                {f === "all" ? "All questions" : "Mistakes only"}
              </button>
            ))}
          </div>
        </div>
        {[1, 2, 3, 4].map((no) => {
          const partItems = items.filter((i) => i.section_no === no);
          if (!partItems.length) return null;
          return (
            <div key={no} className="space-y-2">
              <h3 className="text-sm font-semibold text-muted-foreground">
                {partNoun} {no}
              </h3>
              <ol className="space-y-2">
                {partItems.map((i) => (
                  <ReviewRow
                    key={i.question_id}
                    item={i}
                    stem={stems.get(i.question_id)}
                    options={options.get(i.question_id) ?? new Map()}
                  />
                ))}
              </ol>
            </div>
          );
        })}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">No mistakes — every question was correct.</p>
        )}
      </section>
      <div className="flex justify-center">
        <Button asChild variant="outline">
          <Link href={`${base}/tests/${r.attempt.test_id}`}>
            <RotateCcwIcon aria-hidden="true" />
            Take this test again
          </Link>
        </Button>
      </div>
    </div>
  );
}
