"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchPreview } from "@/lib/admin/listening-api";
import { useModuleInfo } from "@/lib/admin/module";
import { messageFor } from "@/lib/auth/api";
import { queryKeys } from "@/lib/query/keys";

type Answer = { band: number | null; body: string; author_note: string | null };
type Task = { task_no: number; prompt_text: string; min_words: number; model_answers: Answer[] };
type Part = {
  part_no: number;
  topic: string;
  cue_card: { prompt: string; points?: string[]; closing?: string | null } | null;
  questions: { text: string; is_follow_up: boolean }[];
  model_answers: Answer[];
};

function Answers({ answers }: { answers: Answer[] }) {
  if (!answers.length) return null;
  return (
    <details className="rounded-md border bg-muted/30 p-3 text-sm">
      <summary className="cursor-pointer font-medium">
        Model answers ({answers.length}) — candidates see these only after submitting
      </summary>
      {answers.map((a, i) => (
        <div key={i} className="mt-3 space-y-1">
          {a.band !== null && <p className="text-xs font-semibold">Band {a.band}</p>}
          <p className="whitespace-pre-line">{a.body}</p>
        </div>
      ))}
    </details>
  );
}

/** What a candidate would see for a Writing or Speaking version (plus model answers, staff only). */
export function ProductivePreview({ versionId }: { versionId: string }) {
  const { base } = useModuleInfo();
  const q = useQuery({
    queryKey: queryKeys.listening.preview(versionId),
    queryFn: () => fetchPreview(versionId),
  });
  if (q.isPending) return <LoadingState label="Loading preview…" />;
  if (q.isError)
    return <ErrorState title="Preview unavailable" description={messageFor(q.error)} />;
  const p = q.data;
  const tasks = (p.writing_tasks ?? []) as Task[];
  const parts = (p.speaking_parts ?? []) as Part[];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl font-semibold">{p.title}</h1>
          <p className="text-sm text-muted-foreground">
            Candidate preview · v{p.version_no} · {p.status.replace("_", " ")}. Not an attempt:
            nothing is stored.
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href={`${base}/${versionId}`}>Back to the editor</Link>
        </Button>
      </div>
      {tasks.map((t) => (
        <Card key={t.task_no}>
          <CardContent className="space-y-3 pt-6">
            <h2 className="font-heading text-lg font-semibold">Writing Task {t.task_no}</h2>
            <p className="whitespace-pre-line">{t.prompt_text || "No prompt yet."}</p>
            <p className="text-sm text-muted-foreground">Write at least {t.min_words} words.</p>
            <Answers answers={t.model_answers} />
          </CardContent>
        </Card>
      ))}
      {parts.map((part) => (
        <Card key={part.part_no}>
          <CardContent className="space-y-3 pt-6">
            <h2 className="font-heading text-lg font-semibold">
              Speaking Part {part.part_no}: {part.topic || "No topic yet"}
            </h2>
            {part.cue_card && (
              <div className="rounded-lg border p-4">
                <p className="font-medium">{part.cue_card.prompt}</p>
                {part.cue_card.points?.length ? (
                  <>
                    <p className="mt-2 text-sm">You should say:</p>
                    <ul className="list-disc pl-6 text-sm">
                      {part.cue_card.points.map((pt) => (
                        <li key={pt}>{pt}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
                {part.cue_card.closing && <p className="mt-1 text-sm">{part.cue_card.closing}</p>}
              </div>
            )}
            <ol className="list-decimal space-y-1 pl-6 text-sm">
              {part.questions.map((qq, i) => (
                <li key={i}>
                  {qq.text}
                  {qq.is_follow_up && <span className="text-muted-foreground"> (follow-up)</span>}
                </li>
              ))}
            </ol>
            <Answers answers={part.model_answers} />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
