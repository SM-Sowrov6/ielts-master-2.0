"use client";

import { AlertTriangleIcon, LoaderCircleIcon, RotateCcwIcon, SparklesIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Evaluation } from "@/lib/practice/api";

const KIND: Record<string, string> = {
  grammar: "Grammar",
  vocabulary: "Vocabulary",
  spelling: "Spelling",
  punctuation: "Punctuation",
  cohesion: "Cohesion",
  task: "Task",
  fluency: "Fluency",
};

/**
 * Honest rendering of an AI evaluation: pending, unavailable, failed and rejected states say so
 * plainly and never show a number. Bands appear only for a succeeded evaluation.
 */
export function EvaluationView({
  evaluation,
  retrying,
  onRetry,
}: {
  evaluation: Evaluation | null | undefined;
  retrying: boolean;
  onRetry: () => void;
}) {
  if (!evaluation) return null;
  const e = evaluation;
  if (e.status === "queued" || e.status === "running") {
    return (
      <div role="status" className="flex items-center gap-3 rounded-xl border bg-card p-5">
        <LoaderCircleIcon className="size-5 animate-spin text-primary" aria-hidden="true" />
        <div>
          <p className="font-medium">Your response is being assessed…</p>
          <p className="text-sm text-muted-foreground">
            This usually takes under a minute. You can leave this page; the result is saved.
          </p>
        </div>
      </div>
    );
  }
  if (e.status !== "succeeded") {
    const title =
      e.status === "unavailable"
        ? "AI evaluation is not available yet"
        : e.status === "rejected_input"
          ? "This response could not be assessed"
          : "The assessment did not complete";
    return (
      <div role="alert" className="space-y-3 rounded-xl border border-warning/40 bg-warning/10 p-5">
        <p className="flex items-center gap-2 font-medium">
          <AlertTriangleIcon className="size-5" aria-hidden="true" />
          {title}
        </p>
        <p className="text-sm">
          {e.message ??
            "Something went wrong while assessing your response. No score has been given."}
        </p>
        <p className="text-xs text-muted-foreground">
          Your response is saved. No band score is shown because none was produced.
        </p>
        {e.retryable && (
          <Button variant="outline" size="sm" onClick={onRetry} disabled={retrying}>
            <RotateCcwIcon aria-hidden="true" />
            Try the assessment again
          </Button>
        )}
      </div>
    );
  }
  return (
    <section aria-labelledby="eval-h" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4 rounded-2xl border bg-card p-5 shadow-elevation-1">
        <div>
          <h2 id="eval-h" className="flex items-center gap-2 font-heading text-xl font-semibold">
            <SparklesIcon className="size-5 text-primary" aria-hidden="true" />
            AI-estimated assessment
          </h2>
          <p className="max-w-prose text-sm text-muted-foreground">
            An estimate from an AI examiner using the platform&apos;s published rubric — not an
            official IELTS score.
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Overall band (estimate)</p>
          <p className="font-heading text-4xl font-bold">
            {e.band_overall !== null ? e.band_overall.toFixed(1) : "—"}
          </p>
          {e.band_overall === null && e.not_assessed.length > 0 && (
            <p className="max-w-56 text-xs text-muted-foreground">
              No overall band: {e.not_assessed.join(", ")} could not be assessed from audio yet.
            </p>
          )}
        </div>
      </div>
      {e.off_topic && (
        <p role="alert" className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
          The assessor judged this response not to address the task.
        </p>
      )}
      {e.summary && <p className="rounded-lg bg-muted/50 p-4 text-sm">{e.summary}</p>}
      <ul className="grid gap-4 md:grid-cols-2">
        {e.criteria.map((c) => (
          <li key={c.code} className="space-y-2 rounded-xl border bg-card p-4">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="font-semibold">{c.name}</h3>
              <span className="font-heading text-2xl font-bold">{c.band.toFixed(1)}</span>
            </div>
            <p className="text-sm text-muted-foreground">{c.rationale}</p>
            {c.strengths.length > 0 && (
              <div className="text-sm">
                <p className="font-medium text-success">Strengths</p>
                <ul className="list-disc pl-5">
                  {c.strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {c.improvements.length > 0 && (
              <div className="text-sm">
                <p className="font-medium">To improve</p>
                <ul className="list-disc pl-5">
                  {c.improvements.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
        {e.not_assessed.map((code) => (
          <li
            key={code}
            className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground"
          >
            <h3 className="font-semibold text-foreground">
              {code === "PR" ? "Pronunciation" : code}
            </h3>
            Not assessed: pronunciation is measured from audio by a dedicated assessor, which is not
            configured yet. It is never guessed from a transcript.
          </li>
        ))}
      </ul>
      {e.improvement_plan.length > 0 && (
        <section aria-labelledby="plan-h" className="space-y-2 rounded-xl border bg-card p-4">
          <h3 id="plan-h" className="font-heading text-lg font-semibold">
            Your improvement plan
          </h3>
          <ol className="list-decimal space-y-1 pl-5 text-sm">
            {e.improvement_plan.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </section>
      )}
      {e.feedback.length > 0 && (
        <section aria-labelledby="fb-h" className="space-y-2">
          <h3 id="fb-h" className="font-heading text-lg font-semibold">
            Line-by-line feedback
          </h3>
          <ul className="space-y-2">
            {e.feedback.map((f, i) => (
              <li key={i} className="rounded-lg border p-3 text-sm">
                <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {KIND[f.kind] ?? f.kind}
                </p>
                <p>
                  <span className="rounded bg-destructive/10 px-1 line-through decoration-destructive/60">
                    {f.excerpt}
                  </span>{" "}
                  → <span className="rounded bg-success/10 px-1">{f.suggestion}</span>
                </p>
                <p className="text-muted-foreground">{f.explanation}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="text-xs text-muted-foreground">
        Assessed by {e.provider ?? "AI"}
        {e.model ? ` (${e.model})` : ""} · prompt {e.prompt_version ?? "—"}
      </p>
    </section>
  );
}

export function ModelAnswers({
  answers,
}: {
  answers: { band: number | null; body: string; author_note: string | null }[];
}) {
  if (!answers.length) return null;
  return (
    <section aria-labelledby="ma-h" className="space-y-3">
      <h2 id="ma-h" className="font-heading text-lg font-semibold">
        Model answer{answers.length > 1 ? "s" : ""}
      </h2>
      {answers.map((a, i) => (
        <details key={i} className="rounded-xl border bg-card p-4" open={i === 0}>
          <summary className="cursor-pointer font-medium">
            {a.band !== null ? `Band ${a.band.toFixed(1)} sample` : `Sample ${i + 1}`}
          </summary>
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed">{a.body}</p>
          {a.author_note && <p className="mt-2 text-xs text-muted-foreground">{a.author_note}</p>}
        </details>
      ))}
    </section>
  );
}
