"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRightIcon,
  AudioLinesIcon,
  ClockIcon,
  LoaderCircleIcon,
  MicIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ExaminerAvatar, ExaminerCard } from "@/components/speaking-room/shared";
import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/lib/auth/api";
import { fetchSpeakingTests } from "@/lib/practice/api";
import {
  DIFFICULTY,
  createRoom,
  fetchExaminers,
  fetchRoomTests,
  fetchRooms,
  type RoomSummary,
} from "@/lib/practice/room-api";
import { cn } from "@/lib/utils";

const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

function statusLabel(r: RoomSummary): string {
  if (r.status !== "completed") return r.status === "live" ? "In progress" : "Not started";
  if (r.band_overall !== null) return `Band ${r.band_overall.toFixed(1)}`;
  if (r.evaluation_status === "queued" || r.evaluation_status === "running") return "Assessing";
  if (r.evaluation_status) return "Evaluation pending";
  return "No answers recorded";
}

export function SpeakingLanding() {
  const examiners = useQuery({ queryKey: ["speaking", "examiners"], queryFn: fetchExaminers });
  const rooms = useQuery({ queryKey: ["speaking", "rooms"], queryFn: fetchRooms });
  const tests = useQuery({ queryKey: ["speaking", "room-tests"], queryFn: fetchRoomTests });
  const quick = useQuery({ queryKey: ["speaking", "tests"], queryFn: fetchSpeakingTests });
  const done = rooms.data?.filter((r) => r.status === "completed") ?? [];
  const minutes = Math.round(done.reduce((n, r) => n + (r.duration_seconds ?? 0), 0) / 60);
  const banded = done.filter((r) => r.band_overall !== null);
  const latestBand = banded[0]?.band_overall ?? null;

  return (
    <div className="space-y-12">
      <section className="relative overflow-hidden rounded-3xl border bg-gradient-to-br from-primary/10 via-background to-info/10 p-6 shadow-elevation-1 sm:p-10">
        <div className="grid items-center gap-8 lg:grid-cols-[1.3fr_1fr]">
          <div className="space-y-5">
            <p className="inline-flex items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-xs font-semibold tracking-wide text-primary uppercase">
              <SparklesIcon className="size-3.5" aria-hidden="true" />
              AI Speaking Room
            </p>
            <h1 className="font-heading text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
              Speak with an AI examiner,
              <br className="hidden sm:block" /> the way the real test feels.
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              A full IELTS Speaking test: introduction and interview, the cue-card long turn with
              one minute to prepare, and a two-way discussion. Every line is kept in your
              transcript.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button asChild size="lg" className="h-12 px-6 text-base shadow-elevation-2">
                <Link href="/speaking/start">
                  <MicIcon aria-hidden="true" />
                  Start Speaking Practice
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="h-12 px-6 text-base">
                <a href="#examiners">Meet the examiners</a>
              </Button>
            </div>
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheckIcon className="size-4" aria-hidden="true" />
              The microphone is used only after you start a check or enter a room.
            </p>
          </div>
          <div className="relative hidden justify-center lg:flex" aria-hidden="true">
            <div className="flex items-end gap-6">
              {(examiners.data ?? []).slice(0, 3).map((e, i) => (
                <div
                  key={e.id}
                  className={cn("flex flex-col items-center gap-2", i === 1 && "-translate-y-6")}
                >
                  <ExaminerAvatar examiner={e} size={i === 1 ? "xl" : "lg"} speaking={i === 1} />
                  <span className="text-sm font-medium">{e.name}</span>
                </div>
              ))}
            </div>
            <AudioLinesIcon className="absolute -bottom-2 size-16 text-primary/20" />
          </div>
        </div>
      </section>

      <section aria-label="Your progress" className="grid gap-4 sm:grid-cols-3">
        {[
          { label: "Sessions completed", value: rooms.isPending ? "…" : String(done.length) },
          {
            label: "Minutes spoken with an examiner",
            value: rooms.isPending ? "…" : String(minutes),
          },
          {
            label: "Latest estimated band",
            value: latestBand !== null ? latestBand.toFixed(1) : "—",
          },
        ].map((s) => (
          <div key={s.label} className="rounded-2xl border bg-card p-5">
            <p className="text-sm text-muted-foreground">{s.label}</p>
            <p className="font-heading text-3xl font-semibold">{s.value}</p>
          </div>
        ))}
      </section>

      <section id="examiners" aria-labelledby="ex-h" className="scroll-mt-24 space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="ex-h" className="font-heading text-2xl font-semibold">
            Choose your examiner
          </h2>
          <p className="text-sm text-muted-foreground">
            Each examiner runs the same test in a different style.
          </p>
        </div>
        {examiners.isPending ? (
          <LoadingState label="Loading examiners…" />
        ) : examiners.isError ? (
          <ErrorState
            title="Examiners could not be loaded"
            description={messageFor(examiners.error)}
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-3">
            {examiners.data.map((e) => (
              <li key={e.id} className="flex">
                <div className="flex w-full flex-col">
                  <ExaminerCard examiner={e} />
                  <Button asChild variant="outline" className="mt-2">
                    <Link href={`/speaking/start?examiner=${e.id}`}>Practise with {e.name}</Link>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="recent-h" className="space-y-4">
        <h2 id="recent-h" className="font-heading text-2xl font-semibold">
          Recent sessions
        </h2>
        {rooms.isPending ? (
          <LoadingState rows={2} />
        ) : rooms.isError ? (
          <ErrorState title="Sessions could not be loaded" description={messageFor(rooms.error)} />
        ) : rooms.data.length === 0 ? (
          <EmptyState
            icon={MicIcon}
            title="No sessions yet"
            description="Your speaking sessions, transcripts and evaluations will appear here."
          />
        ) : (
          <ul className="divide-y rounded-2xl border bg-card">
            {rooms.data.slice(0, 8).map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <p className="font-medium">{r.test_title}</p>
                  <p className="text-xs text-muted-foreground">
                    with {r.examiner_name} · {dateTime.format(new Date(r.created_at))}
                    {r.duration_seconds
                      ? ` · ${Math.max(1, Math.round(r.duration_seconds / 60))} min`
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={r.band_overall !== null ? "default" : "outline"}>
                    {statusLabel(r)}
                  </Badge>
                  <Button asChild size="sm" variant="outline">
                    <Link href={`/speaking/rooms/${r.id}`}>
                      {r.status === "completed" ? "Review" : "Continue"}
                    </Link>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="tests-h" className="space-y-4">
        <h2 id="tests-h" className="font-heading text-2xl font-semibold">
          Speaking tests
        </h2>
        {tests.data && tests.data.length > 0 ? (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {tests.data.map((t) => (
              <li key={t.config_id} className="space-y-2 rounded-2xl border bg-card p-5">
                <h3 className="font-heading text-lg font-semibold">{t.test_title}</h3>
                <p className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <ClockIcon className="size-3.5" aria-hidden="true" />≤ {t.max_total_minutes} min
                  </span>
                  <span>· Part 1: {t.part1_questions} questions</span>
                  <span>· Part 3: {t.part3_questions} questions</span>
                  <span>· {DIFFICULTY[t.difficulty]}</span>
                </p>
                <Button asChild size="sm">
                  <Link href={`/speaking/start?test=${t.config_id}`}>
                    Take this test <ArrowRightIcon aria-hidden="true" />
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            {tests.isPending ? "Loading…" : "No examiner-ready tests are published yet."}
          </p>
        )}
        {quick.data && quick.data.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Prefer to practise one part at a time?{" "}
            <Link
              href="/speaking/practice"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Use the question-by-question recorder
            </Link>
            .
          </p>
        )}
      </section>
    </div>
  );
}

// ------------------------------------------------------------------------------ start
export function StartSpeaking() {
  const router = useRouter();
  const params = useSearchParams();
  const examiners = useQuery({ queryKey: ["speaking", "examiners"], queryFn: fetchExaminers });
  const tests = useQuery({ queryKey: ["speaking", "room-tests"], queryFn: fetchRoomTests });
  const [examinerId, setExaminer] = useState<string | null>(params.get("examiner"));
  const [configId, setConfig] = useState<string | null>(params.get("test"));
  const [record, setRecord] = useState(false);
  const [process, setProcess] = useState(false);
  const create = useMutation({
    mutationFn: (v: { examiner: string; config: string }) => createRoom(v.examiner, v.config),
    onSuccess: (room) => router.push(`/speaking/rooms/${room.id}`),
    onError: (e) => toast.error(messageFor(e)),
  });
  if (examiners.isPending || tests.isPending) return <LoadingState label="Preparing…" />;
  if (examiners.isError || tests.isError)
    return (
      <ErrorState
        title="Speaking is not available"
        description={messageFor(examiners.error ?? tests.error)}
      />
    );
  const chosenTest = configId ?? (tests.data.length === 1 ? tests.data[0]!.config_id : null);
  const ready = examinerId && chosenTest && record && process;
  return (
    <div className="space-y-8">
      <div className="space-y-1">
        <Link href="/speaking" className="text-sm text-muted-foreground hover:underline">
          ← Speaking
        </Link>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">
          Set up your speaking room
        </h1>
      </div>
      <section aria-labelledby="s1" className="space-y-3">
        <h2 id="s1" className="font-heading text-lg font-semibold">
          1. Select an AI examiner
        </h2>
        <ul className="grid gap-4 md:grid-cols-3">
          {examiners.data.map((e) => (
            <li key={e.id} className="flex">
              <ExaminerCard
                examiner={e}
                selected={examinerId === e.id}
                onSelect={() => setExaminer(e.id)}
              />
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="s2" className="space-y-3">
        <h2 id="s2" className="font-heading text-lg font-semibold">
          2. Choose a test
        </h2>
        {tests.data.length === 0 ? (
          <p className="rounded-xl border border-dashed p-6 text-sm text-muted-foreground">
            No examiner-ready Speaking test is published yet. Please check back soon.
          </p>
        ) : (
          <fieldset className="grid gap-3 md:grid-cols-2">
            <legend className="sr-only">Speaking test</legend>
            {tests.data.map((t) => (
              <label
                key={t.config_id}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border bg-card p-4",
                  chosenTest === t.config_id && "border-primary ring-2 ring-primary/30",
                )}
              >
                <input
                  type="radio"
                  name="test"
                  className="mt-1 size-4 accent-[var(--primary)]"
                  checked={chosenTest === t.config_id}
                  onChange={() => setConfig(t.config_id)}
                />
                <span>
                  <span className="font-medium">{t.test_title}</span>
                  <span className="block text-xs text-muted-foreground">
                    Parts 1–3 · up to {t.max_total_minutes} minutes · {DIFFICULTY[t.difficulty]}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
      </section>
      <section aria-labelledby="s3" className="space-y-3 rounded-2xl border bg-card p-5">
        <h2 id="s3" className="font-heading text-lg font-semibold">
          3. Your consent
        </h2>
        <Label className="flex items-start gap-2 font-normal">
          <Checkbox checked={record} onCheckedChange={(v) => setRecord(Boolean(v))} />
          <span>
            I agree that my voice is recorded and kept privately for up to 30 days so I can review
            the session.
          </span>
        </Label>
        <Label className="flex items-start gap-2 font-normal">
          <Checkbox checked={process} onCheckedChange={(v) => setProcess(Boolean(v))} />
          <span>
            I agree that my recordings and transcript are processed by speech and AI services to
            evaluate my speaking.
          </span>
        </Label>
      </section>
      <Button
        size="lg"
        disabled={!ready || create.isPending}
        onClick={() =>
          examinerId && chosenTest && create.mutate({ examiner: examinerId, config: chosenTest })
        }
      >
        {create.isPending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
        Create speaking room
      </Button>
    </div>
  );
}
