"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, HeadphonesIcon, LoaderCircleIcon, PlayIcon, TimerIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { LEVEL } from "@/components/listening/listening-home";
import { typeLabel } from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/errors";
import { messageFor } from "@/lib/auth/api";
import { useExamModule } from "@/lib/exam/module";
import { createAttempt, fetchListeningTest, type Mode } from "@/lib/exam/api";
import { cn } from "@/lib/utils";

const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function TestIntro({ testId }: { testId: string }) {
  const router = useRouter();
  const { module, title, base, examBase, partNoun } = useExamModule();
  const test = useQuery({
    queryKey: ["exam-test", module, testId],
    queryFn: () => fetchListeningTest(testId, module),
  });
  const [mode, setMode] = useState<Mode | null>(null);
  // One idempotency key per (test, mode) for this page: double clicks and network retries
  // return the same server attempt instead of creating duplicates.
  const keys = useRef<Record<string, string>>({});
  const start = useMutation({
    mutationFn: (m: Mode) => {
      keys.current[m] ??= crypto.randomUUID();
      return createAttempt(testId, m, keys.current[m]!, module);
    },
    onSuccess: (attempt) => router.push(`${examBase}/${attempt.id}`),
  });

  if (test.isPending) return <LoadingState label="Loading test…" />;
  if (test.isError) {
    return (
      <ErrorState
        title={
          test.error instanceof ApiError && test.error.status === 404
            ? "This test is not available"
            : "The test could not be loaded"
        }
        description={messageFor(test.error)}
        action={
          <Button asChild variant="outline">
            <Link href={base}>Back to {title}</Link>
          </Button>
        }
      />
    );
  }
  const t = test.data;
  const chosen = mode ?? t.default_mode;
  const rules = t.modes.find((m) => m.mode === chosen) ?? t.modes[0]!;
  const open = t.progress.open_attempt_id;
  const openError = start.error instanceof ApiError && start.error.code === "attempt_open_exists";

  return (
    <div className="space-y-8">
      <Button asChild variant="ghost" size="sm">
        <Link href={base}>
          <ArrowLeftIcon aria-hidden="true" />
          All {title} tests
        </Link>
      </Button>
      <header className="space-y-2">
        <p className="text-sm text-muted-foreground">
          {t.book_title} · {t.edition_label}
        </p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">{t.title}</h1>
        {t.description && (
          <p className="max-w-[var(--container-prose)] text-muted-foreground">{t.description}</p>
        )}
        <dl className="flex flex-wrap gap-2 pt-2 text-sm">
          <div className="rounded-full bg-muted px-3 py-1">
            <dt className="sr-only">Parts</dt>
            <dd>{t.sections} parts</dd>
          </div>
          <div className="rounded-full bg-muted px-3 py-1">
            <dt className="sr-only">Questions</dt>
            <dd>{t.questions} questions</dd>
          </div>
          <div className="rounded-full bg-muted px-3 py-1">
            <dt className="sr-only">Time</dt>
            <dd>{Math.round(rules.time_limit_seconds / 60)} minutes</dd>
          </div>
          {t.difficulty && (
            <div className="rounded-full bg-muted px-3 py-1">
              <dt className="sr-only">Level</dt>
              <dd>{LEVEL[t.difficulty]}</dd>
            </div>
          )}
        </dl>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section aria-labelledby="parts" className="space-y-3">
          <h2 id="parts" className="font-heading text-lg font-semibold">
            {module === "reading" ? "The three passages" : "The four parts"}
          </h2>
          <ol className="space-y-3">
            {t.section_list.map((s) => (
              <li key={s.section_no} className="flex gap-4 rounded-xl border bg-card p-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 font-heading font-semibold text-primary">
                  {s.section_no}
                </span>
                <div className="min-w-0 space-y-1 text-sm">
                  <p className="font-medium">{s.title ?? `${partNoun} ${s.section_no}`}</p>
                  {s.context && <p className="text-muted-foreground">{s.context}</p>}
                  <p className="text-xs text-muted-foreground">
                    {s.number_from !== null
                      ? `Questions ${s.number_from}–${s.number_to}`
                      : "No questions"}{" "}
                    · {s.question_types.map(typeLabel).join(", ")}
                  </p>
                  {module === "listening" && !s.has_audio && (
                    <p className="text-xs text-destructive">No recording available</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <aside className="space-y-4">
          <section
            aria-labelledby="mode"
            className="space-y-3 rounded-2xl border bg-card p-5 shadow-elevation-1"
          >
            <h2 id="mode" className="font-heading text-lg font-semibold">
              How do you want to take it?
            </h2>
            <div role="radiogroup" aria-labelledby="mode" className="grid gap-2">
              {t.modes.map((m) => (
                <button
                  key={m.mode}
                  type="button"
                  role="radio"
                  aria-checked={chosen === m.mode}
                  onClick={() => setMode(m.mode)}
                  className={cn(
                    "rounded-xl border p-3 text-left text-sm transition-colors hover:bg-muted",
                    chosen === m.mode && "border-primary bg-primary/5",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    {m.mode === "exam" ? (
                      <TimerIcon className="size-4" aria-hidden="true" />
                    ) : (
                      <HeadphonesIcon className="size-4" aria-hidden="true" />
                    )}
                    {m.mode === "exam" ? "Exam mode" : "Practice mode"}
                  </span>
                  <span className="mt-1 block text-muted-foreground">
                    {m.mode === "exam"
                      ? `${Math.round(m.time_limit_seconds / 60)} minutes, timed by the server. Each recording plays ${m.max_plays === 1 ? "once" : `${m.max_plays} times`}, without pausing or rewinding. Answers are submitted automatically when time runs out.`
                      : "Untimed (the official time is shown as a guide). Pause, rewind and replay the recordings. Submit when you are ready."}
                  </span>
                </button>
              ))}
            </div>
            <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">
              <li>Use headphones in a quiet place and check your volume first.</li>
              <li>
                Your answers are saved automatically as you type; you can refresh or reconnect
                without losing them.
              </li>
              <li>Spelling counts. Keep to the word limit given in each instruction.</li>
              <li>Correct answers and explanations are shown after you submit.</li>
            </ul>
            {open ? (
              <Button asChild className="w-full">
                <Link href={`${examBase}/${open}`}>
                  <PlayIcon aria-hidden="true" />
                  Continue your attempt
                </Link>
              </Button>
            ) : null}
            <Button
              className="w-full"
              variant={open ? "outline" : "default"}
              disabled={start.isPending || t.locked}
              onClick={() => start.mutate(chosen)}
            >
              {start.isPending ? (
                <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
              ) : (
                <PlayIcon aria-hidden="true" />
              )}
              {t.locked ? "Not available yet" : `Start ${chosen === "exam" ? "exam" : "practice"}`}
            </Button>
            {start.isError && (
              <p role="alert" className="text-sm text-destructive">
                {openError
                  ? "You already have an unfinished exam-mode attempt for this test. Continue it instead."
                  : messageFor(start.error)}
              </p>
            )}
          </section>
          {t.attempts.length > 0 && (
            <section aria-labelledby="past" className="space-y-2 rounded-2xl border bg-card p-5">
              <h2 id="past" className="font-heading text-base font-semibold">
                Your attempts
              </h2>
              <ul className="divide-y text-sm">
                {t.attempts.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 py-2">
                    <span>
                      {a.mode === "exam" ? "Exam" : "Practice"} ·{" "}
                      {dateTime.format(new Date(a.started_at ?? a.server_now))}
                    </span>
                    {a.status === "completed" ? (
                      <Link
                        className="font-medium text-primary underline-offset-4 hover:underline"
                        href={`${base}/attempts/${a.id}`}
                      >
                        {a.raw_score}/{a.max_score}
                      </Link>
                    ) : (
                      <Link
                        className="text-muted-foreground underline-offset-4 hover:underline"
                        href={`${examBase}/${a.id}`}
                      >
                        In progress
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
