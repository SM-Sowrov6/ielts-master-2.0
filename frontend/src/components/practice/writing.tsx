"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  ClockIcon,
  LoaderCircleIcon,
  PenLineIcon,
  SendIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { FocusShell } from "@/components/layout/focus-shell";
import { SplitPane } from "@/components/listening/split-pane";
import { EvaluationView, ModelAnswers } from "@/components/practice/evaluation-view";
import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/errors";
import { messageFor } from "@/lib/auth/api";
import {
  autosaveSubmission,
  fetchSubmission,
  fetchSubmissions,
  fetchTaskImage,
  fetchWritingTest,
  fetchWritingTests,
  isPending,
  retryWritingEvaluation,
  startSubmission,
  submitSubmission,
  type Submission,
  type SubmissionSummary,
} from "@/lib/practice/api";
import { cn } from "@/lib/utils";

const LEVEL: Record<string, string> = {
  easy: "Beginner",
  medium: "Intermediate",
  hard: "Advanced",
};
const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function countWords(text: string): number {
  return text.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g)?.length ?? 0;
}

function clock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  return `${m}:${String(seconds % 60).padStart(2, "0")}`;
}

function SubmissionBadge({ s }: { s: SubmissionSummary }) {
  if (s.status === "draft") return <Badge variant="outline">Draft</Badge>;
  if (s.band_overall !== null) return <Badge>Band {s.band_overall.toFixed(1)}</Badge>;
  const label: Record<string, string> = {
    queued: "Assessing",
    running: "Assessing",
    unavailable: "Assessment unavailable",
    failed: "Assessment failed",
    rejected_input: "Not assessable",
    succeeded: "Assessed",
  };
  return <Badge variant="secondary">{label[s.evaluation_status ?? ""] ?? "Submitted"}</Badge>;
}

// ------------------------------------------------------------------------------ home
export function WritingHome() {
  const tests = useQuery({ queryKey: ["writing", "tests"], queryFn: fetchWritingTests });
  const mine = useQuery({ queryKey: ["writing", "submissions"], queryFn: fetchSubmissions });
  return (
    <div className="space-y-10">
      <section className="space-y-2">
        <p className="text-sm font-semibold tracking-wide text-primary uppercase">Module 03</p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">Writing practice</h1>
        <p className="max-w-2xl text-muted-foreground">
          Task 1 and Task 2 prompts with autosave, a live word count and the suggested timing. After
          you submit, an AI examiner estimates your band against the platform&apos;s rubric and
          shows line-by-line feedback and a model answer.
        </p>
      </section>
      <section aria-labelledby="w-tests" className="space-y-4">
        <h2 id="w-tests" className="font-heading text-xl font-semibold">
          Writing tests
        </h2>
        {tests.isPending ? (
          <LoadingState label="Loading Writing tests…" />
        ) : tests.isError ? (
          <ErrorState title="Tests could not be loaded" description={messageFor(tests.error)} />
        ) : tests.data.length === 0 ? (
          <EmptyState
            icon={PenLineIcon}
            title="No Writing tests published yet"
            description="New tests appear here as soon as the content team publishes them."
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tests.data.map((t) => (
              <li
                key={t.test_id}
                className="flex flex-col gap-3 rounded-2xl border bg-card p-5 shadow-elevation-1"
              >
                <p className="text-xs text-muted-foreground">{t.book_title}</p>
                <h3 className="font-heading text-lg font-semibold">{t.title}</h3>
                {t.description && (
                  <p className="line-clamp-2 text-sm text-muted-foreground">{t.description}</p>
                )}
                <div className="flex flex-wrap gap-2 text-xs">
                  {t.difficulty && <Badge variant="outline">{LEVEL[t.difficulty]}</Badge>}
                  <Badge variant="outline">Task 1 + Task 2</Badge>
                </div>
                <Button asChild className="mt-auto">
                  <Link href={`/writing/tests/${t.test_id}`}>Open test</Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="w-mine" className="space-y-4">
        <h2 id="w-mine" className="font-heading text-xl font-semibold">
          Your responses
        </h2>
        {mine.isPending ? (
          <LoadingState rows={2} />
        ) : mine.isError ? (
          <ErrorState
            title="Your responses could not be loaded"
            description={messageFor(mine.error)}
          />
        ) : mine.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">You have not written anything yet.</p>
        ) : (
          <ul className="divide-y rounded-xl border">
            {mine.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-medium">Task {s.task_no}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.word_count} words ·{" "}
                    {dateTime.format(new Date(s.submitted_at ?? s.updated_at))}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <SubmissionBadge s={s} />
                  <Button asChild size="sm" variant="outline">
                    <Link
                      href={
                        s.status === "draft"
                          ? `/exam/writing/${s.id}`
                          : `/writing/submissions/${s.id}`
                      }
                    >
                      {s.status === "draft" ? "Continue" : "View result"}
                    </Link>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

// ------------------------------------------------------------------------------ test
function TaskImage({ testId, taskNo }: { testId: string; taskNo: number }) {
  const url = useQuery({
    queryKey: ["writing", "image", testId, taskNo],
    queryFn: () => fetchTaskImage(testId, taskNo),
    staleTime: 4 * 60 * 1000,
  });
  if (url.isPending) return <div className="h-48 animate-pulse rounded-lg bg-muted" />;
  if (url.isError)
    return <p className="text-sm text-destructive">The task visual could not be loaded.</p>;
  return (
    // eslint-disable-next-line @next/next/no-img-element -- short-lived presigned URL from private storage
    <img
      src={url.data}
      alt={`Task ${taskNo} visual`}
      className="max-h-96 rounded-lg border bg-white object-contain"
    />
  );
}

export function WritingTest({ testId }: { testId: string }) {
  const router = useRouter();
  const test = useQuery({
    queryKey: ["writing", "test", testId],
    queryFn: () => fetchWritingTest(testId),
  });
  const start = useMutation({
    mutationFn: (taskNo: 1 | 2) => startSubmission(testId, taskNo),
    onSuccess: (s) => router.push(`/exam/writing/${s.id}`),
    onError: (e) => toast.error(messageFor(e)),
  });
  if (test.isPending) return <LoadingState label="Loading the test…" />;
  if (test.isError)
    return (
      <ErrorState
        title="This test is not available"
        description={messageFor(test.error)}
        action={
          <Button asChild variant="outline">
            <Link href="/writing">Back to Writing</Link>
          </Button>
        }
      />
    );
  const d = test.data;
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/writing">
          <ArrowLeftIcon aria-hidden="true" />
          All Writing tests
        </Link>
      </Button>
      <div className="space-y-1">
        <h1 className="font-heading text-3xl font-semibold tracking-tight">{d.test.title}</h1>
        <p className="text-muted-foreground">
          {d.variant === "academic" ? "Academic" : "General Training"} Writing · {d.test.book_title}
        </p>
      </div>
      <ol className="grid gap-5 lg:grid-cols-2">
        {d.tasks.map((t) => {
          const mine = d.submissions.filter((s) => s.task_no === t.task_no);
          const draft = mine.find((s) => s.status === "draft");
          return (
            <li
              key={t.task_no}
              className="flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-elevation-1"
            >
              <div className="flex items-center justify-between">
                <h2 className="font-heading text-xl font-semibold">Task {t.task_no}</h2>
                <span className="flex items-center gap-1 text-sm text-muted-foreground">
                  <ClockIcon className="size-4" aria-hidden="true" />
                  {t.suggested_minutes} min · {t.min_words}+ words
                </span>
              </div>
              <p className="line-clamp-4 whitespace-pre-line text-sm">{t.prompt_text}</p>
              {mine.length > 0 && (
                <ul className="space-y-1 text-sm">
                  {mine.map((s) => (
                    <li key={s.id} className="flex items-center justify-between gap-2">
                      <Link
                        href={
                          s.status === "draft"
                            ? `/exam/writing/${s.id}`
                            : `/writing/submissions/${s.id}`
                        }
                        className="underline-offset-4 hover:underline"
                      >
                        {s.status === "draft"
                          ? "Your draft"
                          : `Submitted ${dateTime.format(new Date(s.submitted_at!))}`}
                      </Link>
                      <SubmissionBadge s={s} />
                    </li>
                  ))}
                </ul>
              )}
              <Button
                className="mt-auto"
                onClick={() => start.mutate(t.task_no as 1 | 2)}
                disabled={start.isPending}
              >
                {draft ? "Continue your draft" : mine.length ? "Write it again" : "Start writing"}
              </Button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ------------------------------------------------------------------------------ editor
type SaveState = "saved" | "saving" | "unsaved" | "offline" | "conflict";
const AUTOSAVE_MS = 1500;

function Editor({ initial }: { initial: Submission }) {
  const qc = useQueryClient();
  const backupKey = `writing-draft:${initial.id}`;
  // A longer copy kept on this device (e.g. the network dropped before the last autosave).
  const [restored] = useState<string | null>(() => {
    try {
      const local = localStorage.getItem(backupKey);
      return local && local !== initial.body && local.length > initial.body.length ? local : null;
    } catch {
      return null;
    }
  });
  const [body, setBody] = useState(restored ?? initial.body);
  const [state, setState] = useState<SaveState>(restored ? "unsaved" : "saved");
  const [confirming, setConfirming] = useState(false);
  const [elapsed, setElapsed] = useState(initial.time_spent_seconds);
  const elapsedRef = useRef(initial.time_spent_seconds);
  const revision = useRef(initial.client_revision);
  const saved = useRef(initial.body);
  const submitKey = useRef<string | null>(null);
  const words = countWords(body);
  const target = initial.task.suggested_minutes * 60;

  useEffect(() => {
    const t = setInterval(() => {
      elapsedRef.current += 1;
      setElapsed(elapsedRef.current);
    }, 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (restored) toast.info("Restored unsaved text from this device.");
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on mount
  }, []);

  const persist = useCallback(
    async (text: string) => {
      if (text === saved.current) return;
      setState("saving");
      const next = Math.max(revision.current + 1, Date.now());
      try {
        const out = await autosaveSubmission(initial.id, {
          body: text,
          client_revision: next,
          time_spent_seconds: elapsedRef.current,
        });
        revision.current = out.client_revision;
        saved.current = text;
        setState("saved");
        try {
          localStorage.removeItem(backupKey);
        } catch {
          /* ignore */
        }
      } catch (e) {
        if (e instanceof ApiError && e.code === "stale_revision") setState("conflict");
        else setState("offline");
      }
    },
    [initial.id, backupKey],
  );

  useEffect(() => {
    if (body === saved.current) return;
    try {
      localStorage.setItem(backupKey, body);
    } catch {
      /* ignore */
    }
    setState("unsaved");
    const t = setTimeout(() => void persist(body), AUTOSAVE_MS);
    return () => clearTimeout(t);
  }, [body, persist, backupKey]);

  useEffect(() => {
    if (state === "saved") return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [state]);

  const submit = useMutation({
    mutationFn: () => {
      submitKey.current ??= crypto.randomUUID();
      return submitSubmission(
        initial.id,
        {
          body,
          client_revision: Math.max(revision.current + 1, Date.now()),
          time_spent_seconds: elapsed,
        },
        submitKey.current,
      );
    },
    onSuccess: (s) => {
      try {
        localStorage.removeItem(backupKey);
      } catch {
        /* ignore */
      }
      qc.setQueryData(["writing", "submission", initial.id], s);
      void qc.invalidateQueries({ queryKey: ["writing"] });
      setConfirming(false);
      toast.success("Submitted. Your response is being assessed.");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const label: Record<SaveState, string> = {
    saved: "All changes saved",
    saving: "Saving…",
    unsaved: "Unsaved changes",
    offline: "Not saved — check your connection; we keep retrying",
    conflict: "This draft was changed in another tab. Reload to continue.",
  };
  const short = words < initial.task.min_words;

  return (
    <FocusShell
      fill
      title={`${initial.test_title} · Writing Task ${initial.task_no}`}
      status={
        <span
          className={cn("font-mono", elapsed > target ? "text-warning" : "text-muted-foreground")}
          aria-label="Time used"
        >
          <ClockIcon className="mr-1 inline size-4" aria-hidden="true" />
          {clock(elapsed)} / {clock(target)}
        </span>
      }
      actions={
        <div className="flex items-center gap-3">
          <p className="hidden items-center gap-1.5 text-xs sm:flex" aria-live="polite">
            {state === "saving" ? (
              <LoaderCircleIcon className="size-3.5 animate-spin" aria-hidden="true" />
            ) : state === "saved" ? (
              <CheckCircle2Icon className="size-3.5 text-success" aria-hidden="true" />
            ) : null}
            <span className={state === "conflict" || state === "offline" ? "text-destructive" : ""}>
              {label[state]}
            </span>
          </p>
          <Button
            size="sm"
            onClick={() => setConfirming(true)}
            disabled={!body.trim() || state === "conflict"}
          >
            <SendIcon aria-hidden="true" />
            Submit
          </Button>
        </div>
      }
    >
      <SplitPane
        left={
          <article
            aria-label={`Writing Task ${initial.task_no}`}
            className="space-y-4 rounded-xl border bg-card p-6"
          >
            <div>
              <h1 className="font-heading text-xl font-semibold">Writing Task {initial.task_no}</h1>
              <p className="text-sm text-muted-foreground">
                You should spend about {initial.task.suggested_minutes} minutes on this task.
              </p>
            </div>
            <div className="space-y-3 text-[1.0625rem] leading-8 whitespace-pre-line">
              {initial.task.prompt_text}
            </div>
            {initial.task.has_image && (
              <TaskImage testId={initial.test_id} taskNo={initial.task_no} />
            )}
            <p className="font-medium">Write at least {initial.task.min_words} words.</p>
          </article>
        }
        right={
          <div className="flex h-full min-h-[24rem] flex-col gap-2">
            <Label htmlFor="w-body" className="sr-only">
              Your response
            </Label>
            <textarea
              id="w-body"
              value={body}
              onChange={(e) => {
                if (e.target.value.length <= 20000) setBody(e.target.value);
              }}
              onBlur={() => void persist(body)}
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="sentences"
              className="min-h-0 w-full flex-1 resize-none rounded-xl border bg-card p-6 text-[1.0625rem] leading-8 [scrollbar-width:thin] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              placeholder="Start writing your response here…"
            />
            <div className="flex shrink-0 items-center justify-between text-sm">
              <span className="text-xs text-muted-foreground">
                Spell-check is off, as in the real test. Your text saves automatically.
              </span>
              <span className={short ? "text-warning" : "text-success"} aria-live="polite">
                Word count: <strong className="tabular-nums">{words}</strong>
              </span>
            </div>
          </div>
        }
      />
      <Dialog open={confirming} onOpenChange={(o) => !submit.isPending && setConfirming(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit your response?</DialogTitle>
            <DialogDescription>
              You have written {words} words
              {short ? `, fewer than the ${initial.task.min_words} required` : ""}. After
              submitting, the text can no longer change.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirming(false)}
              disabled={submit.isPending}
            >
              Keep writing
            </Button>
            <Button onClick={() => submit.mutate()} disabled={submit.isPending}>
              {submit.isPending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
              Submit for assessment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </FocusShell>
  );
}

/** Full-screen writing room for a draft; a submitted response goes to its result page. */
export function WritingExam({ submissionId }: { submissionId: string }) {
  const router = useRouter();
  const sub = useQuery({
    queryKey: ["writing", "submission", submissionId],
    queryFn: () => fetchSubmission(submissionId),
  });
  const submitted = sub.data?.status === "submitted";
  useEffect(() => {
    if (submitted) router.replace(`/writing/submissions/${submissionId}`);
  }, [submitted, router, submissionId]);
  if (sub.isPending || submitted)
    return (
      <FocusShell title="Writing">
        <LoadingState label="Opening your writing task…" />
      </FocusShell>
    );
  if (sub.isError)
    return (
      <FocusShell title="Writing">
        <ErrorState
          title="This response could not be opened"
          description={messageFor(sub.error)}
          action={
            <Button asChild variant="outline">
              <Link href="/writing">Back to Writing</Link>
            </Button>
          }
        />
      </FocusShell>
    );
  return <Editor initial={sub.data} />;
}

export function WritingSubmission({ submissionId }: { submissionId: string }) {
  const qc = useQueryClient();
  const sub = useQuery({
    queryKey: ["writing", "submission", submissionId],
    queryFn: () => fetchSubmission(submissionId),
    refetchInterval: (q) => (isPending(q.state.data?.evaluation) ? 3000 : false),
  });
  const retry = useMutation({
    mutationFn: () => retryWritingEvaluation(submissionId),
    onSuccess: (s) => qc.setQueryData(["writing", "submission", submissionId], s),
    onError: (e) => toast.error(messageFor(e)),
  });
  if (sub.isPending) return <LoadingState label="Loading your response…" />;
  if (sub.isError)
    return (
      <ErrorState
        title="This response could not be opened"
        description={messageFor(sub.error)}
        action={
          <Button asChild variant="outline">
            <Link href="/writing">Back to Writing</Link>
          </Button>
        }
      />
    );
  const s = sub.data;
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href={`/writing/tests/${s.test_id}`}>
          <ArrowLeftIcon aria-hidden="true" />
          {s.test_title}
        </Link>
      </Button>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <aside className="space-y-3 lg:sticky lg:top-20 lg:self-start">
          <h1 className="font-heading text-2xl font-semibold">Writing Task {s.task_no}</h1>
          <p className="text-sm text-muted-foreground">
            Spend about {s.task.suggested_minutes} minutes. Write at least {s.task.min_words} words.
          </p>
          <div className="rounded-xl border bg-card p-4 whitespace-pre-line">
            {s.task.prompt_text}
          </div>
          {s.task.has_image && <TaskImage testId={s.test_id} taskNo={s.task_no} />}
        </aside>
        <div className="space-y-6">
          {s.status === "draft" ? (
            <div className="space-y-3 rounded-xl border bg-card p-6">
              <p>This response is still a draft.</p>
              <Button asChild>
                <Link href={`/exam/writing/${s.id}`}>Continue writing</Link>
              </Button>
            </div>
          ) : (
            <>
              <EvaluationView
                evaluation={s.evaluation}
                retrying={retry.isPending}
                onRetry={() => retry.mutate()}
              />
              <section aria-labelledby="yr-h" className="space-y-2">
                <h2 id="yr-h" className="font-heading text-lg font-semibold">
                  Your response · {s.word_count} words
                </h2>
                <div className="rounded-xl border bg-card p-5 whitespace-pre-line leading-relaxed">
                  {s.body}
                </div>
              </section>
              <ModelAnswers answers={s.model_answers} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
