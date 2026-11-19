"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeftIcon, HistoryIcon } from "lucide-react";
import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { messageFor } from "@/lib/auth/api";
import { useExamModule } from "@/lib/exam/module";
import { fetchHistory } from "@/lib/exam/api";

const dateTime = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

export function AttemptHistory() {
  const { module, title, base, examBase } = useExamModule();
  const history = useQuery({
    queryKey: ["exam-history", module],
    queryFn: () => fetchHistory(undefined, module),
  });
  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link href={base}>
          <ArrowLeftIcon aria-hidden="true" />
          {title}
        </Link>
      </Button>
      <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
        Your {title} attempts
      </h1>
      {history.isPending ? (
        <LoadingState label="Loading attempts…" />
      ) : history.isError ? (
        <ErrorState title="Attempts could not be loaded" description={messageFor(history.error)} />
      ) : history.data.length === 0 ? (
        <EmptyState
          icon={HistoryIcon}
          title="No attempts yet"
          description="Your completed tests and scores will appear here."
          action={
            <Button asChild>
              <Link href={base}>Find a test</Link>
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-sm">
            <caption className="sr-only">{title} attempts</caption>
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="p-3">
                  Test
                </th>
                <th scope="col" className="p-3">
                  Mode
                </th>
                <th scope="col" className="p-3">
                  Date
                </th>
                <th scope="col" className="p-3 text-right">
                  Score
                </th>
                <th scope="col" className="p-3 text-right">
                  Accuracy
                </th>
                <th scope="col" className="p-3">
                  <span className="sr-only">Action</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {history.data.map((a) => {
                const completed = a.status === "completed";
                return (
                  <tr key={a.id}>
                    <th scope="row" className="p-3 text-left font-medium">
                      {a.test.title}
                    </th>
                    <td className="p-3">{a.mode === "exam" ? "Exam" : "Practice"}</td>
                    <td className="p-3 whitespace-nowrap">
                      {dateTime.format(new Date(a.completed_at ?? a.started_at ?? a.server_now))}
                    </td>
                    <td className="p-3 text-right tabular-nums">
                      {completed
                        ? `${a.raw_score}/${a.max_score}`
                        : `${a.answered ?? 0}/${a.questions_total} answered`}
                    </td>
                    <td className="p-3 text-right tabular-nums">
                      {completed && a.max_score
                        ? `${Math.round(((a.raw_score ?? 0) / a.max_score) * 1000) / 10}%`
                        : "—"}
                    </td>
                    <td className="p-3 text-right">
                      {completed ? (
                        <Link
                          className="font-medium text-primary underline-offset-4 hover:underline"
                          href={`${base}/attempts/${a.id}`}
                        >
                          Review
                        </Link>
                      ) : a.status === "in_progress" || a.status === "created" ? (
                        <Link
                          className="font-medium text-primary underline-offset-4 hover:underline"
                          href={`${examBase}/${a.id}`}
                        >
                          Continue
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
