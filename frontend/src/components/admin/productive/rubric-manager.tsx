"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckIcon, LoaderCircleIcon, PlusIcon, SaveIcon, Trash2Icon } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { IssueList } from "@/components/admin/listening/editor/question-editor";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ContentValidationError } from "@/lib/admin/listening-api";
import {
  createRubric,
  deleteRubric,
  fetchRubrics,
  reviewRubric,
  rubricAction,
  saveRubric,
  type Rubric,
  type RubricCriterion,
  type RubricModule,
} from "@/lib/admin/productive-api";
import type { Me } from "@/lib/auth/api";
import { messageFor } from "@/lib/auth/api";

const KEY = (module: RubricModule) => ["admin", "rubrics", module] as const;

function CriterionEditor({
  criterion,
  readOnly,
  onChange,
}: {
  criterion: RubricCriterion;
  readOnly: boolean;
  onChange: (c: RubricCriterion) => void;
}) {
  const id = useId();
  const bands = criterion.bands ?? [];
  return (
    <fieldset className="space-y-3 rounded-lg border p-4">
      <legend className="px-1 font-semibold">
        {criterion.code} · {criterion.name}
      </legend>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-name`}>Name</Label>
        <Input
          id={`${id}-name`}
          value={criterion.name}
          readOnly={readOnly}
          maxLength={120}
          onChange={(e) => onChange({ ...criterion, name: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-desc`}>What this criterion assesses</Label>
        <Textarea
          id={`${id}-desc`}
          rows={2}
          value={criterion.description ?? ""}
          readOnly={readOnly}
          maxLength={2000}
          onChange={(e) => onChange({ ...criterion, description: e.target.value })}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        Band descriptors in your own words (at least three bands). The AI evaluator uses this text
        as its marking guide.
      </p>
      {bands.map((b, i) => (
        <div key={i} className="flex items-start gap-2">
          <Input
            aria-label={`Band for descriptor ${i + 1}`}
            type="number"
            min={0}
            max={9}
            className="w-20"
            value={b.band}
            readOnly={readOnly}
            onChange={(e) =>
              onChange({
                ...criterion,
                bands: bands.map((x, j) => (j === i ? { ...x, band: Number(e.target.value) } : x)),
              })
            }
          />
          <Textarea
            aria-label={`Descriptor ${i + 1}`}
            rows={2}
            value={b.descriptor}
            readOnly={readOnly}
            maxLength={1000}
            onChange={(e) =>
              onChange({
                ...criterion,
                bands: bands.map((x, j) => (j === i ? { ...x, descriptor: e.target.value } : x)),
              })
            }
          />
          {!readOnly && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={`Remove descriptor ${i + 1}`}
              onClick={() => onChange({ ...criterion, bands: bands.filter((_, j) => j !== i) })}
            >
              <Trash2Icon aria-hidden="true" />
            </Button>
          )}
        </div>
      ))}
      {!readOnly && bands.length < 10 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            onChange({
              ...criterion,
              bands: [...bands, { band: Math.max(0, 9 - bands.length), descriptor: "" }],
            })
          }
        >
          <PlusIcon aria-hidden="true" />
          Add band descriptor
        </Button>
      )}
    </fieldset>
  );
}

function RubricCard({ rubric, user, module }: { rubric: Rubric; user: Me; module: RubricModule }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(rubric.title);
  const [note, setNote] = useState(rubric.change_note ?? "");
  const [criteria, setCriteria] = useState<RubricCriterion[]>(
    rubric.criteria.map((c) => ({ ...c, bands: c.bands.map((b) => ({ ...b })) })),
  );
  const [comment, setComment] = useState("");
  const [issues, setIssues] = useState(rubric.issues);
  const can = (p: string) => user.permissions.includes(p);
  const editable = rubric.status === "draft" && can("content.edit");
  const isAuthor = rubric.created_by === user.id;
  const refresh = () => qc.invalidateQueries({ queryKey: KEY(module) });
  const onError = (e: unknown) => {
    if (e instanceof ContentValidationError) setIssues(e.issues);
    toast.error(messageFor(e));
  };
  const save = useMutation({
    mutationFn: () =>
      saveRubric(rubric.id, {
        revision: rubric.revision,
        title: title.trim(),
        change_note: note.trim() || null,
        criteria,
      }),
    onSuccess: (r) => {
      setIssues(r.issues);
      toast.success("Rubric saved.");
      void refresh();
    },
    onError,
  });
  const act = useMutation({
    mutationFn: async (
      a: "submit" | "publish" | "approve" | "changes" | "delete",
    ): Promise<unknown> =>
      a === "approve" || a === "changes"
        ? reviewRubric(rubric.id, a === "approve" ? "approved" : "changes_requested", comment)
        : a === "delete"
          ? deleteRubric(rubric.id)
          : rubricAction(rubric.id, a),
    onSuccess: () => {
      toast.success("Done.");
      void refresh();
    },
    onError,
  });
  const status = rubric.approved ? "approved" : rubric.status;
  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-heading text-lg font-semibold">
            Version {rubric.version_no}: {rubric.title}
          </h2>
          <Badge variant={status === "published" ? "default" : "outline"}>
            {status.replace("_", " ")}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Created by {rubric.created_by_name ?? "unknown"}
          {rubric.published_at && ` · published ${new Date(rubric.published_at).toLocaleString()}`}
        </p>
        {editable && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`t-${rubric.id}`}>Title</Label>
              <Input
                id={`t-${rubric.id}`}
                value={title}
                maxLength={200}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`n-${rubric.id}`}>Change note</Label>
              <Input
                id={`n-${rubric.id}`}
                value={note}
                maxLength={2000}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
        )}
        <IssueList issues={issues} />
        <div className="space-y-3">
          {criteria.map((c, i) => (
            <CriterionEditor
              key={c.code}
              criterion={c}
              readOnly={!editable}
              onChange={(next) => setCriteria(criteria.map((x, j) => (j === i ? next : x)))}
            />
          ))}
        </div>
        {rubric.reviews.length > 0 && (
          <ul className="space-y-1 text-sm">
            {rubric.reviews.map((r, i) => (
              <li key={i}>
                <span className="font-medium">{r.reviewer_name ?? "Reviewer"}</span>:{" "}
                {r.decision === "approved" ? "approved" : "requested changes"}
                {r.comment && ` — ${r.comment}`}
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          {editable && (
            <>
              <Button onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending ? (
                  <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
                ) : (
                  <SaveIcon aria-hidden="true" />
                )}
                Save
              </Button>
              <Button
                variant="outline"
                onClick={() => act.mutate("submit")}
                disabled={act.isPending}
              >
                Submit for review
              </Button>
              <Button variant="ghost" onClick={() => act.mutate("delete")} disabled={act.isPending}>
                Delete draft
              </Button>
            </>
          )}
          {rubric.status === "in_review" &&
            can("content.review") &&
            !isAuthor &&
            !rubric.approved && (
              <div className="flex w-full flex-wrap items-end gap-2">
                <div className="min-w-48 flex-1 space-y-1.5">
                  <Label htmlFor={`c-${rubric.id}`}>Review comment</Label>
                  <Input
                    id={`c-${rubric.id}`}
                    value={comment}
                    maxLength={2000}
                    onChange={(e) => setComment(e.target.value)}
                  />
                </div>
                <Button onClick={() => act.mutate("approve")} disabled={act.isPending}>
                  <CheckIcon aria-hidden="true" />
                  Approve
                </Button>
                <Button
                  variant="outline"
                  onClick={() => act.mutate("changes")}
                  disabled={act.isPending}
                >
                  Request changes
                </Button>
              </div>
            )}
          {rubric.status === "in_review" && isAuthor && (
            <p className="text-sm text-muted-foreground">
              Waiting for review by another staff member (four-eyes rule).
            </p>
          )}
          {rubric.approved && can("content.publish") && (
            <Button onClick={() => act.mutate("publish")} disabled={act.isPending}>
              Publish (replaces the current rubric)
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function RubricManager({ user, module }: { user: Me; module: RubricModule }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: KEY(module), queryFn: () => fetchRubrics(module) });
  const create = useMutation({
    mutationFn: () => createRubric(module),
    onSuccess: () => {
      toast.success("Draft rubric created from the latest version.");
      void qc.invalidateQueries({ queryKey: KEY(module) });
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  if (list.isPending) return <LoadingState label="Loading rubrics…" />;
  if (list.isError)
    return <ErrorState title="Rubrics could not be loaded" description={messageFor(list.error)} />;
  const open = list.data.some((r) => r.status === "draft" || r.status === "in_review");
  const published = list.data.find((r) => r.status === "published");
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {published
          ? `AI evaluations use version ${published.version_no}. New evaluations pick up a newly published version; past results keep the version they used.`
          : "No rubric is published yet, so AI evaluation reports itself as unavailable to candidates."}
      </p>
      {user.permissions.includes("content.edit") && !open && (
        <Button onClick={() => create.mutate()} disabled={create.isPending}>
          <PlusIcon aria-hidden="true" />
          New rubric version
        </Button>
      )}
      {list.data.length === 0 && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          No rubric versions yet.
        </p>
      )}
      {list.data.map((r) => (
        <RubricCard key={`${r.id}-${r.revision}`} rubric={r} user={user} module={module} />
      ))}
    </div>
  );
}
