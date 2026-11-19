"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  LoaderCircleIcon,
  MicIcon,
  RotateCcwIcon,
  SendIcon,
  SquareIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { EvaluationView, ModelAnswers } from "@/components/practice/evaluation-view";
import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/lib/auth/api";
import {
  fetchRecordingUrl,
  fetchSpeakingSession,
  fetchSpeakingSessions,
  fetchSpeakingTest,
  fetchSpeakingTests,
  isPending,
  retrySpeakingEvaluation,
  startSpeakingSession,
  submitSpeakingSession,
  uploadRecording,
  type SpeakingItem,
  type SpeakingMode,
} from "@/lib/practice/api";
import { cn } from "@/lib/utils";

const MODES: { value: SpeakingMode; label: string }[] = [
  { value: "full", label: "Full test (Parts 1–3, about 11–14 minutes)" },
  { value: "part1", label: "Part 1 only: interview" },
  { value: "part2", label: "Part 2 only: cue card long turn" },
  { value: "part3", label: "Part 3 only: discussion" },
];
const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

function preferredMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

// ------------------------------------------------------------------------------ home
export function SpeakingHome() {
  const tests = useQuery({ queryKey: ["speaking", "tests"], queryFn: fetchSpeakingTests });
  const mine = useQuery({ queryKey: ["speaking", "sessions"], queryFn: fetchSpeakingSessions });
  return (
    <div className="space-y-10">
      <section className="space-y-2">
        <p className="text-sm font-semibold tracking-wide text-primary uppercase">Module 04</p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">Speaking practice</h1>
        <p className="max-w-2xl text-muted-foreground">
          Answer real-format Part 1, 2 and 3 questions out loud. Your answers are recorded in the
          browser, stored privately, transcribed and assessed against the platform&apos;s rubric.
        </p>
      </section>
      <section aria-labelledby="s-tests" className="space-y-4">
        <h2 id="s-tests" className="font-heading text-xl font-semibold">
          Speaking tests
        </h2>
        {tests.isPending ? (
          <LoadingState label="Loading Speaking tests…" />
        ) : tests.isError ? (
          <ErrorState title="Tests could not be loaded" description={messageFor(tests.error)} />
        ) : tests.data.length === 0 ? (
          <EmptyState
            icon={MicIcon}
            title="No Speaking tests published yet"
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
                <Button asChild className="mt-auto">
                  <Link href={`/speaking/tests/${t.test_id}`}>Open test</Link>
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-labelledby="s-mine" className="space-y-4">
        <h2 id="s-mine" className="font-heading text-xl font-semibold">
          Your sessions
        </h2>
        {mine.isPending ? (
          <LoadingState rows={2} />
        ) : mine.isError ? (
          <ErrorState
            title="Your sessions could not be loaded"
            description={messageFor(mine.error)}
          />
        ) : mine.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No sessions yet.</p>
        ) : (
          <ul className="divide-y rounded-xl border">
            {mine.data.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-medium">
                    {MODES.find((m) => m.value === s.mode)?.label.split(" (")[0]}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {dateTime.format(new Date(s.created_at))}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {s.band_overall !== null ? (
                    <Badge>Band {s.band_overall.toFixed(1)}</Badge>
                  ) : (
                    <Badge variant="outline">
                      {s.status === "recording"
                        ? "In progress"
                        : (s.evaluation_status ?? "Submitted")}
                    </Badge>
                  )}
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/speaking/sessions/${s.id}`}>
                      {s.status === "recording" ? "Continue" : "View result"}
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

// ------------------------------------------------------------------------------ test + consent
export function SpeakingTest({ testId }: { testId: string }) {
  const router = useRouter();
  const test = useQuery({
    queryKey: ["speaking", "test", testId],
    queryFn: () => fetchSpeakingTest(testId),
  });
  const [mode, setMode] = useState<SpeakingMode>("full");
  const [processing, setProcessing] = useState(false);
  const [recording, setRecording] = useState(false);
  const start = useMutation({
    mutationFn: () => startSpeakingSession(testId, mode),
    onSuccess: (s) => router.push(`/speaking/sessions/${s.id}`),
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
            <Link href="/speaking">Back to Speaking</Link>
          </Button>
        }
      />
    );
  const d = test.data;
  const supported =
    typeof window !== "undefined" && !!navigator.mediaDevices && preferredMime() !== "";
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/speaking">
          <ArrowLeftIcon aria-hidden="true" />
          All Speaking tests
        </Link>
      </Button>
      <h1 className="font-heading text-3xl font-semibold tracking-tight">{d.test.title}</h1>
      <ol className="grid gap-4 md:grid-cols-3">
        {d.parts.map((p) => (
          <li key={p.part_no} className="rounded-2xl border bg-card p-5">
            <h2 className="font-heading text-lg font-semibold">Part {p.part_no}</h2>
            <p className="text-sm font-medium">{p.topic}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {p.part_no === 2
                ? "1 minute to prepare, then speak for up to 2 minutes."
                : `${p.questions.length} question${p.questions.length === 1 ? "" : "s"}, about ${p.answer_seconds} seconds each.`}
            </p>
          </li>
        ))}
      </ol>
      <form
        className="space-y-4 rounded-2xl border bg-card p-5"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <fieldset className="space-y-2">
          <legend className="font-semibold">What do you want to practise?</legend>
          {MODES.map((m) => (
            <label key={m.value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="mode"
                value={m.value}
                checked={mode === m.value}
                onChange={() => setMode(m.value)}
                className="size-4 accent-[var(--primary)]"
              />
              {m.label}
            </label>
          ))}
        </fieldset>
        <fieldset className="space-y-3 rounded-lg bg-muted/40 p-4">
          <legend className="px-1 font-semibold">Your consent (required)</legend>
          <Label className="flex items-start gap-2 font-normal">
            <Checkbox checked={recording} onCheckedChange={(v) => setRecording(Boolean(v))} />
            <span>
              I agree that my voice is <strong>recorded</strong> and stored privately for up to 30
              days so I can replay my answers.
            </span>
          </Label>
          <Label className="flex items-start gap-2 font-normal">
            <Checkbox checked={processing} onCheckedChange={(v) => setProcessing(Boolean(v))} />
            <span>
              I agree that my recordings are <strong>processed</strong> by speech-to-text and AI
              assessment services to give me feedback.
            </span>
          </Label>
          <p className="text-xs text-muted-foreground">
            Consent version {d.consent_version}. You can stop at any time.
          </p>
        </fieldset>
        {!supported && (
          <p role="alert" className="text-sm text-destructive">
            This browser cannot record audio. Use a recent version of Chrome, Edge, Firefox or
            Safari.
          </p>
        )}
        <Button type="submit" disabled={!processing || !recording || !supported || start.isPending}>
          {start.isPending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
          Start speaking
        </Button>
      </form>
    </div>
  );
}

// ------------------------------------------------------------------------------ recorder
export function Playback({ sessionId, recordingId }: { sessionId: string; recordingId: string }) {
  const url = useQuery({
    queryKey: ["speaking", "audio", recordingId],
    queryFn: () => fetchRecordingUrl(sessionId, recordingId),
    staleTime: 4 * 60 * 1000,
  });
  if (!url.data) return null;
  return (
    <audio
      controls
      preload="none"
      src={url.data}
      className="h-9 w-full max-w-sm"
      aria-label="Your recorded answer"
    />
  );
}

function Recorder({
  sessionId,
  item,
  onDone,
}: {
  sessionId: string;
  item: SpeakingItem;
  onDone: () => void;
}) {
  const [phase, setPhase] = useState<"idle" | "prep" | "recording" | "uploading">("idle");
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const started = useRef(0);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    if (phase !== "prep" && phase !== "recording") return;
    if (left <= 0) {
      if (phase === "prep") void begin();
      else stop();
      return;
    }
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- countdown driver
  }, [phase, left]);

  async function begin() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = preferredMime();
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: (rec.mimeType || mime).split(";")[0] });
        const duration = Date.now() - started.current;
        if (duration < 1000 || blob.size === 0) {
          setPhase("idle");
          setError("That recording was too short. Try again.");
          return;
        }
        setPhase("uploading");
        try {
          await uploadRecording(
            sessionId,
            { part_no: item.part_no as 1 | 2 | 3, question_no: item.question_no },
            blob,
            duration,
          );
          setPhase("idle");
          onDone();
        } catch (e) {
          setPhase("idle");
          setError(messageFor(e));
        }
      };
      recorder.current = rec;
      started.current = Date.now();
      rec.start(1000);
      setLeft(item.answer_seconds);
      setPhase("recording");
    } catch {
      setPhase("idle");
      setError("Microphone access was blocked. Allow the microphone for this site and try again.");
    }
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  const done = item.recording_status === "ready";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        {phase === "recording" ? (
          <Button variant="destructive" onClick={stop}>
            <SquareIcon aria-hidden="true" />
            Stop ({left}s left)
          </Button>
        ) : phase === "prep" ? (
          <Button variant="outline" onClick={() => void begin()}>
            Preparation: {left}s — start speaking now
          </Button>
        ) : phase === "uploading" ? (
          <Button disabled>
            <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            Saving your answer…
          </Button>
        ) : (
          <Button
            variant={done ? "outline" : "default"}
            onClick={() => {
              if (item.prep_seconds > 0 && !done) {
                setLeft(item.prep_seconds);
                setPhase("prep");
              } else void begin();
            }}
          >
            {done ? <RotateCcwIcon aria-hidden="true" /> : <MicIcon aria-hidden="true" />}
            {done
              ? "Record again"
              : item.prep_seconds
                ? "Start 1-minute preparation"
                : "Record answer"}
          </Button>
        )}
        {phase === "recording" && (
          <span role="status" className="flex items-center gap-2 text-sm text-destructive">
            <span
              className="size-2.5 animate-pulse rounded-full bg-destructive"
              aria-hidden="true"
            />
            Recording
          </span>
        )}
        {done && phase === "idle" && (
          <span className="flex items-center gap-1 text-sm text-success">
            <CheckCircle2Icon className="size-4" aria-hidden="true" />
            Answer saved
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {done && item.recording_id && phase === "idle" && (
        <Playback key={item.recording_id} sessionId={sessionId} recordingId={item.recording_id} />
      )}
    </div>
  );
}

function CueCard({ item }: { item: SpeakingItem }) {
  if (!item.cue_card) return <p className="text-lg font-medium">{item.text}</p>;
  return (
    <div className="rounded-xl border-2 border-dashed bg-muted/30 p-4">
      <p className="text-lg font-medium">{item.cue_card.prompt}</p>
      {item.cue_card.points.length > 0 && (
        <>
          <p className="mt-2 text-sm">You should say:</p>
          <ul className="list-disc pl-6 text-sm">
            {item.cue_card.points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </>
      )}
      {item.cue_card.closing && <p className="mt-1 text-sm">{item.cue_card.closing}</p>}
    </div>
  );
}

export function SpeakingSessionView({ sessionId }: { sessionId: string }) {
  const qc = useQueryClient();
  const key = ["speaking", "session", sessionId];
  const session = useQuery({
    queryKey: key,
    queryFn: () => fetchSpeakingSession(sessionId),
    refetchInterval: (q) => (isPending(q.state.data?.evaluation) ? 3000 : false),
  });
  const submitKey = useRef<string | null>(null);
  const submit = useMutation({
    mutationFn: () => {
      submitKey.current ??= crypto.randomUUID();
      return submitSpeakingSession(sessionId, submitKey.current);
    },
    onSuccess: (s) => {
      qc.setQueryData(key, s);
      void qc.invalidateQueries({ queryKey: ["speaking", "sessions"] });
      toast.success("Submitted. Your answers are being assessed.");
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const retry = useMutation({
    mutationFn: () => retrySpeakingEvaluation(sessionId),
    onSuccess: (s) => qc.setQueryData(key, s),
    onError: (e) => toast.error(messageFor(e)),
  });
  if (session.isPending) return <LoadingState label="Loading your session…" />;
  if (session.isError)
    return (
      <ErrorState
        title="This session could not be opened"
        description={messageFor(session.error)}
        action={
          <Button asChild variant="outline">
            <Link href="/speaking">Back to Speaking</Link>
          </Button>
        }
      />
    );
  const s = session.data;
  const recordingMode = s.status === "recording";
  const ready = s.items.filter((i) => i.recording_status === "ready").length;
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href="/speaking">
          <ArrowLeftIcon aria-hidden="true" />
          Speaking
        </Link>
      </Button>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold">{s.test_title}</h1>
          <p className="text-sm text-muted-foreground">
            {recordingMode
              ? `${ready} of ${s.items.length} answers recorded`
              : `Submitted ${dateTime.format(new Date(s.submitted_at!))}${s.audio_purge_after ? ` · audio kept until ${dateTime.format(new Date(s.audio_purge_after))}` : ""}`}
          </p>
        </div>
        {recordingMode && (
          <Button
            onClick={() => submit.mutate()}
            disabled={ready < s.items.length || submit.isPending}
          >
            {submit.isPending ? (
              <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            ) : (
              <SendIcon aria-hidden="true" />
            )}
            Submit for assessment
          </Button>
        )}
      </div>
      {!recordingMode && (
        <EvaluationView
          evaluation={s.evaluation}
          retrying={retry.isPending}
          onRetry={() => retry.mutate()}
        />
      )}
      <ol className="space-y-4">
        {s.items.map((item) => (
          <li
            key={`${item.part_no}-${item.question_no}`}
            className={cn(
              "space-y-3 rounded-2xl border bg-card p-5",
              item.recording_status === "ready" && recordingMode && "border-success/40",
            )}
          >
            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Part {item.part_no}
              {item.part_no !== 2 && ` · Question ${item.question_no}`}
            </p>
            <CueCard item={item} />
            {recordingMode ? (
              <Recorder
                sessionId={sessionId}
                item={item}
                onDone={() => void qc.invalidateQueries({ queryKey: key })}
              />
            ) : (
              <>
                {item.recording_id && (
                  <Playback sessionId={sessionId} recordingId={item.recording_id} />
                )}
                {item.transcript && (
                  <p className="rounded-lg bg-muted/50 p-3 text-sm">
                    <span className="font-medium">Transcript (automatic): </span>
                    {item.transcript}
                  </p>
                )}
              </>
            )}
          </li>
        ))}
      </ol>
      {!recordingMode && <ModelAnswers answers={s.model_answers} />}
    </div>
  );
}
