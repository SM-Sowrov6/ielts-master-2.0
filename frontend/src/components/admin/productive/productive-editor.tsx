"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircleIcon, LockIcon, PlusIcon, SaveIcon, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useState } from "react";
import { toast } from "sonner";

import { MediaField } from "@/components/admin/listening/editor/media-field";
import { IssueList } from "@/components/admin/listening/editor/question-editor";
import { WorkflowPanel } from "@/components/admin/listening/editor/workflow-panel";
import { StatusBadge } from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { countErrors } from "@/lib/admin/issues";
import {
  ContentValidationError,
  fetchEditorDocument,
  type Asset,
  type EditorDocument,
  type Issue,
} from "@/lib/admin/listening-api";
import { useModuleInfo } from "@/lib/admin/module";
import {
  productiveBody,
  saveProductiveDraft,
  type ModelAnswerDoc,
  type SpeakingPartDoc,
  type WritingTaskDoc,
} from "@/lib/admin/productive-api";
import type { Me } from "@/lib/auth/api";
import { messageFor } from "@/lib/auth/api";
import { queryKeys } from "@/lib/query/keys";

type Draft = {
  title: string;
  description: string;
  minutes: string;
  adminNotes: string;
  changeNote: string;
  tasks: WritingTaskDoc[];
  parts: SpeakingPartDoc[];
};

function fromDoc(doc: EditorDocument): Draft {
  return {
    title: doc.test.title,
    description: doc.version.description ?? "",
    minutes: doc.duration_seconds ? String(Math.round(doc.duration_seconds / 60)) : "",
    adminNotes: doc.test.admin_notes ?? "",
    changeNote: doc.version.change_note ?? "",
    tasks: structuredClone(doc.writing_tasks ?? []),
    parts: structuredClone(doc.speaking_parts ?? []),
  };
}

const lines = (text: string) =>
  text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

function issuesAt(issues: readonly Issue[], fragment: string) {
  return issues.filter((i) => i.location.includes(fragment));
}

function ModelAnswers({
  answers,
  readOnly,
  onChange,
}: {
  answers: ModelAnswerDoc[];
  readOnly: boolean;
  onChange: (next: ModelAnswerDoc[]) => void;
}) {
  const id = useId();
  const set = (i: number, patch: Partial<ModelAnswerDoc>) =>
    onChange(answers.map((a, j) => (j === i ? { ...a, ...patch } : a)));
  return (
    <fieldset className="space-y-3 rounded-lg border p-3">
      <legend className="px-1 text-sm font-semibold">Model answers</legend>
      <p className="text-xs text-muted-foreground">
        Shown to candidates only after they submit. Write your own sample answers; do not paste
        copyrighted material.
      </p>
      {answers.length === 0 && <p className="text-sm text-muted-foreground">None yet.</p>}
      {answers.map((a, i) => (
        <div key={i} className="space-y-2 rounded-md bg-muted/40 p-3">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor={`${id}-band-${i}`}>Band (optional)</Label>
              <Input
                id={`${id}-band-${i}`}
                type="number"
                min={0}
                max={9}
                step={0.5}
                className="w-24"
                value={a.band ?? ""}
                readOnly={readOnly}
                onChange={(e) =>
                  set(i, { band: e.target.value === "" ? null : Number(e.target.value) })
                }
              />
            </div>
            <div className="min-w-48 flex-1 space-y-1">
              <Label htmlFor={`${id}-note-${i}`}>Author note</Label>
              <Input
                id={`${id}-note-${i}`}
                value={a.author_note ?? ""}
                readOnly={readOnly}
                maxLength={2000}
                onChange={(e) => set(i, { author_note: e.target.value || null })}
              />
            </div>
            {!readOnly && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={`Remove model answer ${i + 1}`}
                onClick={() => onChange(answers.filter((_, j) => j !== i))}
              >
                <Trash2Icon aria-hidden="true" />
              </Button>
            )}
          </div>
          <Label htmlFor={`${id}-body-${i}`} className="sr-only">
            Model answer {i + 1}
          </Label>
          <Textarea
            id={`${id}-body-${i}`}
            rows={6}
            value={a.body}
            readOnly={readOnly}
            maxLength={10000}
            onChange={(e) => set(i, { body: e.target.value })}
          />
        </div>
      ))}
      {!readOnly && answers.length < 3 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange([...answers, { band: null, body: "", author_note: null }])}
        >
          <PlusIcon aria-hidden="true" />
          Add model answer
        </Button>
      )}
    </fieldset>
  );
}

function TaskEditor({
  task,
  variant,
  testId,
  assets,
  readOnly,
  issues,
  onAsset,
  onChange,
}: {
  task: WritingTaskDoc;
  variant: string;
  testId: string;
  assets: ReadonlyMap<string, Asset>;
  readOnly: boolean;
  issues: readonly Issue[];
  onAsset: (a: Asset) => void;
  onChange: (t: WritingTaskDoc) => void;
}) {
  const id = useId();
  const kind =
    task.task_no === 2 ? "Essay" : variant === "academic" ? "Report on a visual" : "Letter";
  return (
    <section aria-labelledby={`${id}-h`} className="space-y-4">
      <div>
        <h2 id={`${id}-h`} className="font-heading text-xl font-semibold">
          Task {task.task_no}
        </h2>
        <p className="text-sm text-muted-foreground">
          {kind} · suggested {task.task_no === 1 ? 20 : 40} minutes
        </p>
      </div>
      <IssueList issues={issuesAt(issues, `task ${task.task_no}`)} />
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-prompt`}>Task prompt (shown to candidates)</Label>
        <Textarea
          id={`${id}-prompt`}
          rows={6}
          value={task.prompt_text ?? ""}
          readOnly={readOnly}
          maxLength={5000}
          onChange={(e) => onChange({ ...task, prompt_text: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">Separate paragraphs with a blank line.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-min`}>Minimum words</Label>
          <Input
            id={`${id}-min`}
            type="number"
            min={50}
            max={400}
            value={task.min_words}
            readOnly={readOnly}
            onChange={(e) => onChange({ ...task, min_words: Number(e.target.value) || 0 })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`${id}-kf`}>Assessment focus (one per line, staff only)</Label>
          <Textarea
            id={`${id}-kf`}
            rows={3}
            value={(task.key_features ?? []).join("\n")}
            readOnly={readOnly}
            onChange={(e) => onChange({ ...task, key_features: lines(e.target.value) })}
          />
        </div>
      </div>
      {task.task_no === 1 && (
        <MediaField
          label="Task 1 visual (chart, table, map or diagram)"
          kind="image"
          testId={testId}
          assetId={task.image_asset_id}
          assets={assets}
          readOnly={readOnly}
          onUploaded={(asset) => {
            onAsset(asset);
            onChange({ ...task, image_asset_id: asset.id });
          }}
          onRemove={() => onChange({ ...task, image_asset_id: null })}
        />
      )}
      <ModelAnswers
        answers={task.model_answers ?? []}
        readOnly={readOnly}
        onChange={(model_answers) => onChange({ ...task, model_answers })}
      />
    </section>
  );
}

function PartEditor({
  part,
  readOnly,
  issues,
  onChange,
}: {
  part: SpeakingPartDoc;
  readOnly: boolean;
  issues: readonly Issue[];
  onChange: (p: SpeakingPartDoc) => void;
}) {
  const id = useId();
  const questions = part.questions ?? [];
  const card = part.cue_card;
  return (
    <section aria-labelledby={`${id}-h`} className="space-y-4">
      <div>
        <h2 id={`${id}-h`} className="font-heading text-xl font-semibold">
          Part {part.part_no}
        </h2>
        <p className="text-sm text-muted-foreground">
          {part.part_no === 1
            ? "Introduction and interview: short questions on familiar topics."
            : part.part_no === 2
              ? "Long turn: a cue card, 1 minute to prepare, up to 2 minutes to speak."
              : "Discussion: abstract questions linked to the Part 2 topic."}
        </p>
      </div>
      <IssueList issues={issuesAt(issues, `part ${part.part_no}`)} />
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-topic`}>Topic</Label>
        <Input
          id={`${id}-topic`}
          value={part.topic ?? ""}
          readOnly={readOnly}
          maxLength={300}
          onChange={(e) => onChange({ ...part, topic: e.target.value })}
        />
      </div>
      {part.part_no === 2 && (
        <fieldset className="space-y-3 rounded-lg border p-3">
          <legend className="px-1 text-sm font-semibold">Cue card</legend>
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-cue`}>Task</Label>
            <Input
              id={`${id}-cue`}
              value={card?.prompt ?? ""}
              readOnly={readOnly}
              maxLength={500}
              placeholder="Describe …"
              onChange={(e) =>
                onChange({
                  ...part,
                  cue_card: e.target.value
                    ? { points: [], closing: null, ...card, prompt: e.target.value }
                    : null,
                })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-points`}>You should say (one point per line)</Label>
            <Textarea
              id={`${id}-points`}
              rows={4}
              value={(card?.points ?? []).join("\n")}
              readOnly={readOnly || !card}
              onChange={(e) =>
                card && onChange({ ...part, cue_card: { ...card, points: lines(e.target.value) } })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${id}-closing`}>Closing line</Label>
            <Input
              id={`${id}-closing`}
              value={card?.closing ?? ""}
              readOnly={readOnly || !card}
              maxLength={300}
              placeholder="and explain why …"
              onChange={(e) =>
                card &&
                onChange({ ...part, cue_card: { ...card, closing: e.target.value || null } })
              }
            />
          </div>
        </fieldset>
      )}
      <fieldset className="space-y-2 rounded-lg border p-3">
        <legend className="px-1 text-sm font-semibold">
          {part.part_no === 2 ? "Rounding-off questions" : "Examiner questions"}
        </legend>
        {questions.length === 0 && <p className="text-sm text-muted-foreground">None yet.</p>}
        <ol className="space-y-2">
          {questions.map((q, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <span className="w-6 text-sm text-muted-foreground">{i + 1}.</span>
              <Input
                aria-label={`Question ${i + 1}`}
                className="min-w-48 flex-1"
                value={q.text}
                readOnly={readOnly}
                maxLength={500}
                onChange={(e) =>
                  onChange({
                    ...part,
                    questions: questions.map((x, j) =>
                      j === i ? { ...x, text: e.target.value } : x,
                    ),
                  })
                }
              />
              <Label className="flex items-center gap-1.5 text-xs font-normal">
                <Checkbox
                  checked={Boolean(q.is_follow_up)}
                  disabled={readOnly}
                  onCheckedChange={(v) =>
                    onChange({
                      ...part,
                      questions: questions.map((x, j) =>
                        j === i ? { ...x, is_follow_up: Boolean(v) } : x,
                      ),
                    })
                  }
                />
                Follow-up
              </Label>
              {!readOnly && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove question ${i + 1}`}
                  onClick={() =>
                    onChange({ ...part, questions: questions.filter((_, j) => j !== i) })
                  }
                >
                  <Trash2Icon aria-hidden="true" />
                </Button>
              )}
            </li>
          ))}
        </ol>
        {!readOnly && questions.length < 20 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              onChange({ ...part, questions: [...questions, { text: "", is_follow_up: false }] })
            }
          >
            <PlusIcon aria-hidden="true" />
            Add question
          </Button>
        )}
      </fieldset>
      <ModelAnswers
        answers={part.model_answers ?? []}
        readOnly={readOnly}
        onChange={(model_answers) => onChange({ ...part, model_answers })}
      />
    </section>
  );
}

export function ProductiveEditor({ versionId, user }: { versionId: string; user: Me }) {
  const router = useRouter();
  const { module, base, title } = useModuleInfo();
  const queryClient = useQueryClient();
  const doc = useQuery({
    queryKey: queryKeys.listening.document(versionId),
    queryFn: () => fetchEditorDocument(versionId),
  });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [baseline, setBaseline] = useState("");
  const [loaded, setLoaded] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [extraAssets, setExtraAssets] = useState<Asset[]>([]);
  const dirty = draft !== null && JSON.stringify(draft) !== baseline;
  const remote = doc.data?.version.revision ?? null;
  if (doc.data && remote !== loaded && !dirty) {
    const next = fromDoc(doc.data);
    setDraft(next);
    setBaseline(JSON.stringify(next));
    setLoaded(remote);
  }
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const assets = useMemo(() => {
    const map = new Map<string, Asset>();
    for (const a of [...(doc.data?.assets ?? []), ...extraAssets]) map.set(a.id, a);
    return map;
  }, [doc.data?.assets, extraAssets]);

  const save = useMutation({
    mutationFn: () =>
      saveProductiveDraft(
        versionId,
        productiveBody(doc.data!, {
          revision: loaded!,
          title: draft!.title.trim(),
          description: draft!.description.trim() || null,
          duration_seconds: draft!.minutes ? Math.round(Number(draft!.minutes) * 60) : null,
          admin_notes: draft!.adminNotes.trim() || null,
          change_note: draft!.changeNote.trim() || null,
          writing_tasks: module === "writing" ? draft!.tasks : [],
          speaking_parts: module === "speaking" ? draft!.parts : [],
        }),
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.listening.document(versionId), result.document);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.listening.all,
        refetchType: "inactive",
      });
      setIssues(result.issues);
      const errors = countErrors(result.issues);
      toast.success(
        errors
          ? `Draft saved. ${errors} issue(s) still block submission for review.`
          : "Draft saved. No blocking issues.",
      );
    },
    onError: (e) => {
      if (e instanceof ContentValidationError) {
        setIssues(e.issues);
        toast.error(`Not saved: ${countErrors(e.issues)} error(s) need fixing.`);
      } else toast.error(messageFor(e));
    },
  });

  if (doc.isPending) return <LoadingState label="Loading the test…" />;
  if (doc.isError || !draft)
    return (
      <ErrorState
        title="The test could not be loaded"
        description={messageFor(doc.error)}
        action={
          <Button asChild variant="outline">
            <Link href={base}>Back to {title} Management</Link>
          </Button>
        }
      />
    );
  const d = doc.data;
  const readOnly = d.version.status !== "draft" || !user.permissions.includes("content.edit");
  const patch = (p: Partial<Draft>) => setDraft({ ...draft, ...p });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <Link href={base} className="text-sm text-muted-foreground hover:underline">
            ← {title} Management
          </Link>
          <h1 className="font-heading text-2xl font-semibold tracking-tight">{d.test.title}</h1>
          <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge status={d.version.approved ? "approved" : d.version.status} />
            <span>
              {d.test.code} · v{d.version.version_no} · {d.catalog.book_title}
              {module === "writing" &&
                ` · ${d.variant === "academic" ? "Academic" : "General Training"}`}
            </span>
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link href={`${base}/${versionId}/preview`}>Preview</Link>
          </Button>
          {!readOnly && (
            <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
              {save.isPending ? (
                <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
              ) : (
                <SaveIcon aria-hidden="true" />
              )}
              Save draft
            </Button>
          )}
        </div>
      </div>
      {readOnly && (
        <p className="flex items-center gap-2 rounded-lg border bg-muted/40 px-4 py-3 text-sm">
          <LockIcon className="size-4" aria-hidden="true" />
          This version is {d.version.status.replace("_", " ")} and read-only. Create a new revision
          to change it.
        </p>
      )}
      <IssueList issues={issues.filter((i) => i.location === "test")} />
      <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          <Card>
            <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
              <div className="space-y-1.5 lg:col-span-2">
                <Label htmlFor="pe-title">Test title</Label>
                <Input
                  id="pe-title"
                  value={draft.title}
                  readOnly={readOnly}
                  maxLength={300}
                  onChange={(e) => patch({ title: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pe-minutes">Duration (minutes)</Label>
                <Input
                  id="pe-minutes"
                  type="number"
                  min={1}
                  max={240}
                  value={draft.minutes}
                  readOnly={readOnly}
                  onChange={(e) => patch({ minutes: e.target.value })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pe-change">Change note for reviewers</Label>
                <Input
                  id="pe-change"
                  value={draft.changeNote}
                  readOnly={readOnly}
                  maxLength={2000}
                  onChange={(e) => patch({ changeNote: e.target.value })}
                />
              </div>
              <div className="space-y-1.5 lg:col-span-2">
                <Label htmlFor="pe-desc">Description (shown to candidates)</Label>
                <Textarea
                  id="pe-desc"
                  rows={2}
                  value={draft.description}
                  readOnly={readOnly}
                  maxLength={5000}
                  onChange={(e) => patch({ description: e.target.value })}
                />
              </div>
              <div className="space-y-1.5 lg:col-span-2">
                <Label htmlFor="pe-notes">Internal admin notes</Label>
                <Textarea
                  id="pe-notes"
                  rows={2}
                  value={draft.adminNotes}
                  readOnly={readOnly}
                  maxLength={5000}
                  onChange={(e) => patch({ adminNotes: e.target.value })}
                />
              </div>
            </CardContent>
          </Card>
          {module === "writing"
            ? draft.tasks.map((t, i) => (
                <Card key={t.task_no}>
                  <CardContent className="pt-6">
                    <TaskEditor
                      task={t}
                      variant={d.variant}
                      testId={d.test.id}
                      assets={assets}
                      readOnly={readOnly}
                      issues={issues}
                      onAsset={(a) => setExtraAssets((x) => [...x, a])}
                      onChange={(next) =>
                        patch({ tasks: draft.tasks.map((x, j) => (j === i ? next : x)) })
                      }
                    />
                  </CardContent>
                </Card>
              ))
            : draft.parts.map((p, i) => (
                <Card key={p.part_no}>
                  <CardContent className="pt-6">
                    <PartEditor
                      part={p}
                      readOnly={readOnly}
                      issues={issues}
                      onChange={(next) =>
                        patch({ parts: draft.parts.map((x, j) => (j === i ? next : x)) })
                      }
                    />
                  </CardContent>
                </Card>
              ))}
        </div>
        <div>
          <WorkflowPanel
            doc={d}
            user={user}
            dirty={dirty}
            onIssues={setIssues}
            onDeleted={() => router.push(base)}
            onNavigate={(id) => router.push(`${base}/${id}`)}
          />
        </div>
      </div>
    </div>
  );
}
