"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloudOffIcon,
  LoaderCircleIcon,
  SendIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AudioPlayer } from "@/components/listening/audio-player";
import { QuestionGroup } from "@/components/listening/question-group";
import { PassagePane } from "@/components/listening/passage-pane";
import { SplitPane } from "@/components/listening/split-pane";
import { useExamModule } from "@/lib/exam/module";
import { FocusShell } from "@/components/layout/focus-shell";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/errors";
import { messageFor } from "@/lib/auth/api";
import {
  AnswerQueue,
  forgetAttempt,
  rememberLease,
  storedLease,
  submitKey,
  type FatalCode,
  type SaveState,
} from "@/lib/exam/answer-queue";
import {
  fetchAnswers,
  fetchAttempt,
  fetchContent,
  resumeAttempt,
  startAttempt,
  submitAttempt,
  type Attempt,
  type AttemptContent,
  type Response,
} from "@/lib/exam/api";
import { formatClock, isAnswered, questionRefs, remainingMs } from "@/lib/exam/responses";
import { cn } from "@/lib/utils";

type Phase =
  | { kind: "loading" }
  | { kind: "takeover"; attempt: Attempt }
  | { kind: "ready" }
  | { kind: "error"; message: string };

const SAVE_LABEL: Record<SaveState, string> = {
  idle: "All answers saved",
  pending: "Unsaved changes",
  saving: "Saving…",
  saved: "All answers saved",
  retrying: "Not saved yet",
  stopped: "Saving stopped",
};

function SaveIndicator({ state, detail }: { state: SaveState; detail?: string }) {
  const Icon =
    state === "saving" || state === "pending"
      ? LoaderCircleIcon
      : state === "retrying" || state === "stopped"
        ? CloudOffIcon
        : CheckCircle2Icon;
  return (
    <span
      className={cn(
        "flex items-center gap-1.5 text-xs",
        state === "retrying" || state === "stopped" ? "text-destructive" : "text-muted-foreground",
      )}
      title={detail}
    >
      <Icon
        className={cn("size-3.5", (state === "saving" || state === "pending") && "animate-spin")}
        aria-hidden="true"
      />
      <span>{SAVE_LABEL[state]}</span>
      {detail && state === "retrying" && <span className="sr-only">: {detail}</span>}
    </span>
  );
}

export function ExamRoom({ attemptId }: { attemptId: string }) {
  const router = useRouter();
  const { module, title, base, partNoun } = useExamModule();
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [answers, setAnswers] = useState<Record<string, Response>>({});
  const [section, setSection] = useState(1);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveDetail, setSaveDetail] = useState<string | undefined>();
  const [fatal, setFatal] = useState<FatalCode | null>(null);
  const [offset, setOffset] = useState(0); // server clock - device clock (ms)
  const [now, setNow] = useState(() => Date.now());
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const queue = useRef<AnswerQueue | null>(null);
  const autoSubmitted = useRef(false);

  const content = useQuery({
    queryKey: ["attempt-content", attemptId],
    queryFn: () => fetchContent(attemptId),
    staleTime: Infinity,
    enabled: phase.kind === "ready",
  });

  const syncClock = useCallback((serverNow: string) => {
    const deviceNow = Date.now();
    setOffset(Date.parse(serverNow) - deviceNow);
    setNow(deviceNow);
  }, []);

  const begin = useCallback(
    async (lease: { epoch: number; token: string }, current: Attempt) => {
      setAttempt(current);
      syncClock(current.server_now);
      const q = new AnswerQueue(attemptId, lease, {
        onState: (state, detail) => {
          setSaveState(state);
          setSaveDetail(detail);
        },
        onServerTime: syncClock,
        onFatal: (code) => setFatal(code),
      });
      queue.current?.stop();
      queue.current = q;
      const saved = await fetchAnswers(attemptId);
      const merged: Record<string, Response> = {};
      for (const a of saved.answers) merged[a.question_id] = a.response as Response;
      // Answers typed in this browser but not acknowledged yet win, and are re-sent.
      Object.assign(merged, q.pendingAnswers());
      setAnswers(merged);
      if (q.hasPending()) void q.flush();
      setPhase({ kind: "ready" });
    },
    [attemptId, syncClock],
  );

  // Load: completed -> results; created -> start; running -> reuse this browser's lease or ask.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const current = await fetchAttempt(attemptId);
        if (cancelled) return;
        if (current.status === "completed" || current.status === "submitted") {
          forgetAttempt(attemptId);
          router.replace(`${base}/attempts/${attemptId}`);
          return;
        }
        if (current.status === "created") {
          const lease = await startAttempt(attemptId);
          rememberLease(attemptId, lease.writer_epoch, lease.writer_token);
          await begin({ epoch: lease.writer_epoch, token: lease.writer_token }, lease.attempt);
          return;
        }
        const lease = storedLease(attemptId);
        if (lease && lease.epoch === current.writer_epoch) await begin(lease, current);
        else setPhase({ kind: "takeover", attempt: current });
      } catch (e) {
        if (!cancelled) setPhase({ kind: "error", message: messageFor(e) });
      }
    })();
    return () => {
      cancelled = true;
      queue.current?.stop();
    };
  }, [attemptId, base, begin, router]);

  // Tick the clock; flush when the tab is hidden; warn before leaving with unsaved answers.
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 500);
    const hide = () => document.visibilityState === "hidden" && void queue.current?.flush();
    const leave = (e: BeforeUnloadEvent) => {
      if (queue.current?.hasPending()) e.preventDefault();
    };
    document.addEventListener("visibilitychange", hide);
    window.addEventListener("beforeunload", leave);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", hide);
      window.removeEventListener("beforeunload", leave);
    };
  }, []);

  const sections = useMemo(() => content.data?.sections ?? [], [content.data]);
  const refs = useMemo(() => questionRefs(sections), [sections]);
  const exam = attempt?.mode === "exam";
  const deadline = attempt?.deadline_at ?? null;
  const left = deadline ? remainingMs(deadline, offset, now) : null;
  const timeUp = exam && left !== null && left <= 0;
  const locked = timeUp || fatal !== null || submitting;
  const elapsed = attempt?.started_at ? now + offset - Date.parse(attempt.started_at) : 0;
  const limit =
    Number(
      (attempt?.rules.timing as Record<string, number> | undefined)?.[
        module === "reading" ? "module_seconds" : "listening_seconds"
      ] ?? 0,
    ) *
      1000 +
    Number(
      (attempt?.rules.timing as Record<string, number> | undefined)?.transfer_time_seconds ?? 0,
    ) *
      1000;

  const answeredCount = refs
    .filter((r) => isAnswered(answers[r.id]))
    .reduce((n, r) => n + r.numbers.length, 0);
  const total = refs.reduce((n, r) => n + r.numbers.length, 0);

  const submit = useCallback(async () => {
    const q = queue.current;
    if (!q || !attempt) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await Promise.race([q.flush(), new Promise((r) => setTimeout(r, 4000))]);
      const lease = storedLease(attemptId) ?? { epoch: attempt.writer_epoch, token: "" };
      await submitAttempt(attemptId, lease, submitKey(attemptId), q.finalItems());
      q.stop();
      forgetAttempt(attemptId);
      router.replace(`${base}/attempts/${attemptId}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "attempt_already_submitted") {
        router.replace(`${base}/attempts/${attemptId}`);
        return;
      }
      setSubmitError(messageFor(e));
      setSubmitting(false);
    }
  }, [attempt, attemptId, base, router]);

  // Exam mode: at the deadline, lock and hand in what is saved (the server enforces it anyway).
  useEffect(() => {
    if (timeUp && !autoSubmitted.current && phase.kind === "ready") {
      autoSubmitted.current = true;
      void submit();
    }
  }, [timeUp, phase.kind, submit]);

  const change = (questionId: string, response: Response) => {
    if (locked) return;
    setAnswers((a) => ({ ...a, [questionId]: response }));
    queue.current?.set(questionId, response);
  };

  const goSection = (n: number) => {
    void queue.current?.flush();
    setSection(n);
    window.scrollTo({ top: 0 });
  };

  const jump = (sectionNo: number, number: number) => {
    void queue.current?.flush();
    setSection(sectionNo);
    requestAnimationFrame(() => {
      const el = document.getElementById(`question-${number}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.querySelector<HTMLElement>("input, select")?.focus({ preventScroll: true });
    });
  };

  if (phase.kind === "loading" || (phase.kind === "ready" && content.isPending)) {
    return (
      <FocusShell title={`${title} test`}>
        <LoadingState label="Preparing your test…" />
      </FocusShell>
    );
  }
  if (phase.kind === "error" || content.isError) {
    return (
      <FocusShell title={`${title} test`}>
        <ErrorState
          title="The test could not be opened"
          description={phase.kind === "error" ? phase.message : messageFor(content.error)}
          action={
            <Button asChild variant="outline">
              <Link href={base}>Back to {title}</Link>
            </Button>
          }
        />
      </FocusShell>
    );
  }
  if (phase.kind === "takeover") {
    return (
      <FocusShell title={phase.attempt.test.title}>
        <div className="mx-auto max-w-lg space-y-4 rounded-xl border bg-card p-6 text-center">
          <h1 className="font-heading text-xl font-semibold">Continue this test here?</h1>
          <p className="text-sm text-muted-foreground">
            This attempt was started in another browser or tab. Continuing here makes this device
            the one that saves your answers; the other one will stop saving. Answers that the other
            device had not saved yet cannot be recovered.
          </p>
          <div className="flex justify-center gap-2">
            <Button asChild variant="outline">
              <Link href={base}>Not now</Link>
            </Button>
            <Button
              onClick={async () => {
                try {
                  const lease = await resumeAttempt(attemptId);
                  rememberLease(attemptId, lease.writer_epoch, lease.writer_token);
                  setPhase({ kind: "loading" });
                  await begin(
                    { epoch: lease.writer_epoch, token: lease.writer_token },
                    lease.attempt,
                  );
                } catch (e) {
                  setPhase({ kind: "error", message: messageFor(e) });
                }
              }}
            >
              Continue on this device
            </Button>
          </div>
        </div>
      </FocusShell>
    );
  }

  const data = content.data as AttemptContent;
  const current = data.sections.find((s) => s.section_no === section) ?? data.sections[0];
  if (!attempt || !current) return null;
  const status =
    exam && left !== null ? (
      <span
        className={cn(
          "rounded-md px-2 py-1 font-semibold",
          left < 5 * 60_000 ? "bg-destructive/10 text-destructive" : "bg-muted",
        )}
      >
        <span className="sr-only">Time left </span>
        {formatClock(left)}
      </span>
    ) : (
      <span className="text-muted-foreground">
        <span className="sr-only">Time used </span>
        {formatClock(elapsed)} <span className="text-xs">/ {formatClock(limit)} suggested</span>
      </span>
    );

  return (
    <FocusShell
      title={`${attempt.test.title} · ${exam ? "Exam" : "Practice"}`}
      status={status}
      fill={module === "reading"}
      actions={
        <div className="flex items-center gap-3">
          <SaveIndicator state={saveState} detail={saveDetail} />
          <Button
            size="sm"
            onClick={() => {
              void queue.current?.flush();
              setConfirming(true);
            }}
            disabled={locked}
          >
            <SendIcon aria-hidden="true" />
            <span className="hidden sm:inline">Review &amp; submit</span>
            <span className="sm:hidden">Submit</span>
          </Button>
        </div>
      }
      footer={
        <nav aria-label="Questions" className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={section <= 1}
              onClick={() => goSection(section - 1)}
            >
              <ChevronLeftIcon aria-hidden="true" />
              {partNoun} {section - 1 || ""}
            </Button>
            <p className="text-xs text-muted-foreground tabular-nums" aria-live="polite">
              {answeredCount} of {total} answered
            </p>
            <Button
              variant="outline"
              size="sm"
              disabled={section >= data.sections.length}
              onClick={() => goSection(section + 1)}
            >
              {partNoun} {section < data.sections.length ? section + 1 : ""}
              <ChevronRightIcon aria-hidden="true" />
            </Button>
          </div>
          <ol className="flex flex-wrap gap-1">
            {refs.map((r) => {
              const done = isAnswered(answers[r.id]);
              return (
                <li key={r.id}>
                  <button
                    type="button"
                    onClick={() => jump(r.sectionNo, r.numbers[0]!)}
                    aria-label={`Question ${r.label}, part ${r.sectionNo}, ${done ? "answered" : "not answered"}`}
                    className={cn(
                      "h-7 min-w-7 rounded-md border px-1 text-xs font-medium tabular-nums transition-colors",
                      done
                        ? "border-primary bg-primary text-primary-foreground"
                        : "bg-background hover:bg-muted",
                      r.sectionNo === section && !done && "border-primary/60",
                    )}
                  >
                    {r.label}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>
      }
    >
      <div
        className={module === "reading" ? "flex min-h-0 flex-1 flex-col gap-3" : "space-y-6 pb-4"}
      >
        {fatal && (
          <p
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
          >
            <AlertTriangleIcon
              className="mt-0.5 size-4 shrink-0 text-destructive"
              aria-hidden="true"
            />
            {fatal === "superseded_session"
              ? "This test was continued on another device or tab, so this page can no longer save answers."
              : fatal === "attempt_deadline_passed"
                ? "Time is up. Your saved answers are being submitted."
                : "This attempt can no longer be changed."}
            <Link
              href={`${base}/attempts/${attemptId}`}
              className="ml-auto shrink-0 font-medium underline underline-offset-4"
            >
              View attempt
            </Link>
          </p>
        )}
        {timeUp && !fatal && (
          <p role="status" className="rounded-lg border bg-muted px-4 py-3 text-sm">
            Time is up — saving and submitting your answers…
          </p>
        )}
        <nav aria-label="Test parts">
          <ul className="flex flex-wrap gap-2">
            {data.sections.map((s) => {
              const sectionRefs = refs.filter((r) => r.sectionNo === s.section_no);
              const done = sectionRefs.filter((r) => isAnswered(answers[r.id])).length;
              return (
                <li key={s.section_no}>
                  <button
                    type="button"
                    onClick={() => goSection(s.section_no)}
                    aria-current={s.section_no === section ? "step" : undefined}
                    className={cn(
                      "rounded-full border px-4 py-1.5 text-sm font-medium hover:bg-muted",
                      s.section_no === section &&
                        "border-primary bg-primary text-primary-foreground hover:bg-primary",
                    )}
                  >
                    {partNoun} {s.section_no}
                    <span className="ml-1.5 text-xs opacity-80">
                      {done}/{sectionRefs.length}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <header className="space-y-1">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">
            {partNoun} {current.section_no}
            {current.title ? `: ${current.title}` : ""}
          </h1>
          {current.context && <p className="text-sm text-muted-foreground">{current.context}</p>}
          {current.instructions && <p className="text-sm">{current.instructions}</p>}
        </header>
        {module === "listening" && (
          <AudioPlayer
            key={current.section_no}
            attemptId={attemptId}
            sectionNo={current.section_no}
            exam={exam}
            hasAudio={current.has_audio}
          />
        )}
        {(() => {
          const questions = (
            <div className="space-y-8">
              {current.groups.map((g, i) => (
                <QuestionGroup
                  key={`${current.section_no}-${i}`}
                  group={g}
                  answers={answers}
                  onChange={change}
                  disabled={locked}
                  attemptId={attemptId}
                  sectionNo={current.section_no}
                  groupNo={i + 1}
                />
              ))}
            </div>
          );
          return module === "reading" ? (
            <SplitPane
              left={
                <PassagePane key={current.section_no} passages={current.passages ?? []} embedded />
              }
              right={questions}
            />
          ) : (
            questions
          );
        })()}
      </div>

      <Dialog open={confirming} onOpenChange={(open) => !submitting && setConfirming(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Submit your answers?</DialogTitle>
            <DialogDescription>
              {answeredCount} of {total} questions answered
              {total - answeredCount > 0 ? `, ${total - answeredCount} unanswered` : ""}. After
              submitting you cannot change your answers.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {data.sections.map((s) => {
              const missing = refs.filter(
                (r) => r.sectionNo === s.section_no && !isAnswered(answers[r.id]),
              );
              return (
                <div key={s.section_no} className="flex flex-wrap items-center gap-1 text-sm">
                  <span className="w-16 font-medium">
                    {partNoun} {s.section_no}
                  </span>
                  {missing.length === 0 ? (
                    <span className="text-success">All answered</span>
                  ) : (
                    missing.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        className="rounded border px-1.5 text-xs hover:bg-muted"
                        onClick={() => {
                          setConfirming(false);
                          jump(r.sectionNo, r.numbers[0]!);
                        }}
                      >
                        Q{r.label}
                      </button>
                    ))
                  )}
                </div>
              );
            })}
          </div>
          {submitError && (
            <p role="alert" className="text-sm text-destructive">
              {submitError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)} disabled={submitting}>
              Keep working
            </Button>
            <Button onClick={() => void submit()} disabled={submitting}>
              {submitting && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
              Submit answers
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </FocusShell>
  );
}
