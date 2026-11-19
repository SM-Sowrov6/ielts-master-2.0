"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ClockIcon,
  HeadphonesIcon,
  HistoryIcon,
  LockIcon,
  PlayIcon,
  RotateCcwIcon,
  SearchIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { messageFor } from "@/lib/auth/api";
import { useExamModule } from "@/lib/exam/module";
import { fetchHistory, fetchListeningTests, type ListeningTest } from "@/lib/exam/api";
import { cn } from "@/lib/utils";

export const LEVEL: Record<string, string> = {
  easy: "Beginner",
  medium: "Intermediate",
  hard: "Advanced",
};

type StatusFilter = "all" | "new" | "in_progress" | "completed";

function minutes(seconds: number | null | undefined): string {
  return seconds ? `${Math.round(seconds / 60)} min` : "30 min";
}

function statusOf(t: ListeningTest): Exclude<StatusFilter, "all"> {
  if (t.progress.open_attempt_id) return "in_progress";
  return t.progress.completed > 0 ? "completed" : "new";
}

function TestCard({ test }: { test: ListeningTest }) {
  const { base, examBase } = useExamModule();
  const status = statusOf(test);
  return (
    <li className="flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-elevation-1 transition-shadow hover:shadow-elevation-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-xs font-medium text-muted-foreground">
            {test.book_title} · {test.edition_label}
          </p>
          <h3 className="font-heading text-lg leading-snug font-semibold">
            <Link
              href={`${base}/tests/${test.test_id}`}
              className="underline-offset-4 hover:underline"
            >
              {test.title}
            </Link>
          </h3>
        </div>
        {test.locked ? (
          <Badge variant="outline">
            <LockIcon aria-hidden="true" />
            Premium
          </Badge>
        ) : status === "completed" ? (
          <Badge variant="secondary">Completed</Badge>
        ) : status === "in_progress" ? (
          <Badge className="bg-warning/15 text-foreground">In progress</Badge>
        ) : (
          <Badge variant="outline">New</Badge>
        )}
      </div>
      {test.description && (
        <p className="line-clamp-2 text-sm text-muted-foreground">{test.description}</p>
      )}
      <dl className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-lg bg-muted/60 px-2 py-2">
          <dt className="text-muted-foreground">Parts</dt>
          <dd className="text-sm font-semibold">{test.sections}</dd>
        </div>
        <div className="rounded-lg bg-muted/60 px-2 py-2">
          <dt className="text-muted-foreground">Questions</dt>
          <dd className="text-sm font-semibold">{test.questions}</dd>
        </div>
        <div className="rounded-lg bg-muted/60 px-2 py-2">
          <dt className="text-muted-foreground">Time</dt>
          <dd className="text-sm font-semibold">{minutes(test.duration_seconds)}</dd>
        </div>
      </dl>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {test.difficulty ? LEVEL[test.difficulty] : "All levels"}
          {test.progress.completed > 0 &&
            test.progress.best_raw !== null &&
            ` · Best ${test.progress.best_raw}/${test.questions}`}
        </p>
        {test.locked ? (
          <Button variant="outline" size="sm" disabled>
            Not available yet
          </Button>
        ) : test.progress.open_attempt_id ? (
          <Button asChild size="sm">
            <Link href={`${examBase}/${test.progress.open_attempt_id}`}>
              <PlayIcon aria-hidden="true" />
              Continue
            </Link>
          </Button>
        ) : (
          <Button asChild size="sm" variant={status === "completed" ? "outline" : "default"}>
            <Link href={`${base}/tests/${test.test_id}`}>
              {status === "completed" ? (
                <RotateCcwIcon aria-hidden="true" />
              ) : (
                <PlayIcon aria-hidden="true" />
              )}
              {status === "completed" ? "Practise again" : "Start practice"}
            </Link>
          </Button>
        )}
      </div>
    </li>
  );
}

export function ListeningHome() {
  const { module, title, base, examBase, blurb } = useExamModule();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<"" | "easy" | "medium" | "hard">("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const tests = useQuery({
    queryKey: ["exam-tests", module, query, level],
    queryFn: () => fetchListeningTests({ search: query, difficulty: level || undefined }, module),
  });
  const history = useQuery({
    queryKey: ["exam-history", module],
    queryFn: () => fetchHistory(undefined, module),
  });

  const completed = (history.data ?? []).filter((a) => a.status === "completed");
  const scored = completed.filter((a) => a.max_score);
  const average = scored.length
    ? Math.round(
        (scored.reduce((s, a) => s + (a.raw_score ?? 0) / (a.max_score ?? 1), 0) / scored.length) *
          100,
      )
    : null;
  const best = scored.length ? Math.max(...scored.map((a) => a.raw_score ?? 0)) : null;
  const inProgress = (history.data ?? []).filter((a) => a.status === "in_progress");
  const visible = (tests.data ?? []).filter((t) => status === "all" || statusOf(t) === status);

  return (
    <div className="space-y-8">
      <section
        aria-labelledby="listening-hero"
        className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-elevation-1 sm:p-8"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-20 -right-20 size-64 rounded-full bg-primary/10 blur-3xl"
        />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <p className="flex items-center gap-2 text-sm font-medium text-primary">
              <HeadphonesIcon className="size-4" aria-hidden="true" />
              Listening
            </p>
            <h1
              id="listening-hero"
              className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl"
            >
              {title} practice
            </h1>
            <p className="max-w-[var(--container-prose)] text-muted-foreground">{blurb}</p>
          </div>
          <dl className="grid grid-cols-3 gap-3 text-center lg:min-w-[22rem]">
            <div className="rounded-xl bg-muted/60 px-3 py-3">
              <dt className="text-xs text-muted-foreground">Completed</dt>
              <dd className="font-heading text-xl font-semibold tabular-nums">
                {history.isPending ? "—" : completed.length}
              </dd>
            </div>
            <div className="rounded-xl bg-muted/60 px-3 py-3">
              <dt className="text-xs text-muted-foreground">Average</dt>
              <dd className="font-heading text-xl font-semibold tabular-nums">
                {average === null ? "—" : `${average}%`}
              </dd>
            </div>
            <div className="rounded-xl bg-muted/60 px-3 py-3">
              <dt className="text-xs text-muted-foreground">Best score</dt>
              <dd className="font-heading text-xl font-semibold tabular-nums">
                {best === null ? "—" : `${best}/40`}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      {inProgress.length > 0 && (
        <section aria-labelledby="continue" className="space-y-3">
          <h2 id="continue" className="font-heading text-lg font-semibold">
            Continue where you left off
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {inProgress.map((a) => (
              <li
                key={a.id}
                className="flex items-center justify-between gap-3 rounded-xl border bg-card p-4"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{a.test.title}</p>
                  <p className="flex items-center gap-1 text-xs text-muted-foreground">
                    <ClockIcon className="size-3" aria-hidden="true" />
                    {a.mode === "exam" ? "Exam mode" : "Practice"} · {a.answered ?? 0}/
                    {a.questions_total} answered
                  </p>
                </div>
                <Button asChild size="sm">
                  <Link href={`${examBase}/${a.id}`}>Continue</Link>
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="tests" className="space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="tests" className="font-heading text-lg font-semibold">
            Tests
          </h2>
          <Button asChild variant="ghost" size="sm">
            <Link href={`${base}/history`}>
              <HistoryIcon aria-hidden="true" />
              Your attempts
            </Link>
          </Button>
        </div>
        <form
          role="search"
          className="flex flex-col gap-3 md:flex-row md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            setQuery(search.trim());
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="lt-search">Search tests</Label>
            <div className="flex gap-2">
              <Input
                id="lt-search"
                type="search"
                placeholder="Test or book title"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                maxLength={100}
              />
              <Button type="submit" variant="outline">
                <SearchIcon aria-hidden="true" />
                Search
              </Button>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="lt-level">Level</Label>
            <select
              id="lt-level"
              className="h-9 rounded-md border bg-background px-2 text-sm"
              value={level}
              onChange={(e) => setLevel(e.target.value as typeof level)}
            >
              <option value="">All levels</option>
              <option value="easy">Beginner</option>
              <option value="medium">Intermediate</option>
              <option value="hard">Advanced</option>
            </select>
          </div>
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Status</legend>
            <div className="flex gap-1 rounded-lg border p-1">
              {(["all", "new", "in_progress", "completed"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  aria-pressed={status === s}
                  onClick={() => setStatus(s)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium",
                    status === s ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                  )}
                >
                  {
                    { all: "All", new: "New", in_progress: "In progress", completed: "Completed" }[
                      s
                    ]
                  }
                </button>
              ))}
            </div>
          </fieldset>
        </form>
        {tests.isPending ? (
          <LoadingState label="Loading tests…" rows={3} />
        ) : tests.isError ? (
          <ErrorState
            title="Tests could not be loaded"
            description={messageFor(tests.error)}
            headingLevel={3}
            action={<Button onClick={() => void tests.refetch()}>Try again</Button>}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={HeadphonesIcon}
            headingLevel={3}
            title={
              tests.data.length === 0 && !query && !level
                ? `No ${title} tests published yet`
                : "No tests match"
            }
            description={
              tests.data.length === 0 && !query && !level
                ? "New tests appear here as soon as they are published."
                : "Try another search or filter."
            }
          />
        ) : (
          <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visible.map((t) => (
              <TestCard key={t.test_id} test={t} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
