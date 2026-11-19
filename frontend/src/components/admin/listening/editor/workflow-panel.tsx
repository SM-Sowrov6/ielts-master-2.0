"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArchiveIcon,
  CheckIcon,
  FilePlus2Icon,
  ListChecksIcon,
  LoaderCircleIcon,
  SendIcon,
  Trash2Icon,
  UndoIcon,
  UploadCloudIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { StatusBadge, formatDate } from "@/components/admin/listening/labels";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { countErrors } from "@/lib/admin/issues";
import {
  ContentValidationError,
  deleteDraft,
  fetchValidation,
  newRevision,
  reviewVersion,
  runAction,
  type EditorDocument,
  type Issue,
} from "@/lib/admin/listening-api";
import type { Me } from "@/lib/auth/api";
import { messageFor } from "@/lib/auth/api";
import { useModuleInfo } from "@/lib/admin/module";
import { queryKeys } from "@/lib/query/keys";

/**
 * Lifecycle: draft → (validate) → in review → approved (four-eyes) → published → archived.
 * Buttons appear only when the role and state allow them; the backend enforces the same rules.
 */
export function WorkflowPanel({
  doc,
  user,
  dirty,
  onIssues,
  onDeleted,
  onNavigate,
}: {
  doc: EditorDocument;
  user: Me;
  dirty: boolean;
  onIssues: (issues: Issue[]) => void;
  onDeleted: () => void;
  onNavigate: (versionId: string) => void;
}) {
  const queryClient = useQueryClient();
  const { base } = useModuleInfo();
  const [validation, setValidation] = useState<Issue[] | null>(null);
  const [comment, setComment] = useState("");
  const v = doc.version;
  const can = (p: string) => user.permissions.includes(p);
  const isAuthor = v.created_by === user.id;
  const status = v.approved ? "approved" : v.status;

  const apply = (next: EditorDocument, message: string) => {
    queryClient.setQueryData(queryKeys.listening.document(next.version.id), next);
    void queryClient.invalidateQueries({
      queryKey: queryKeys.listening.all,
      refetchType: "inactive",
    });
    toast.success(message);
  };
  const fail = (e: unknown) => {
    if (e instanceof ContentValidationError) {
      setValidation(e.issues);
      onIssues(e.issues);
      toast.error(`${countErrors(e.issues)} validation error(s) must be fixed first.`);
    } else toast.error(messageFor(e));
  };

  const validate = useMutation({
    mutationFn: () => fetchValidation(v.id),
    onSuccess: (result) => {
      setValidation(result.issues);
      onIssues(result.issues);
    },
    onError: fail,
  });

  async function act(kind: "submit" | "publish" | "archive") {
    try {
      const next = await runAction(v.id, kind);
      apply(
        next,
        {
          submit: "Submitted for review.",
          publish: "Published. This version is now live.",
          archive: "Archived.",
        }[kind],
      );
    } catch (e) {
      fail(e);
    }
  }

  async function review(decision: "approved" | "changes_requested") {
    try {
      apply(
        await reviewVersion(v.id, decision, comment),
        decision === "approved" ? "Approved." : "Changes requested; the version is back in draft.",
      );
      setComment("");
    } catch (e) {
      fail(e);
    }
  }

  const errors = validation ? countErrors(validation) : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-heading text-xl font-semibold">Validate &amp; review</h2>
        <StatusBadge status={status} />
      </div>

      <section className="space-y-3" aria-labelledby="wf-validate">
        <h3 id="wf-validate" className="font-heading text-base font-semibold">
          Validation
        </h3>
        <p className="text-sm text-muted-foreground">
          Checks the saved version at publishing strictness: four sections with audio, 40 questions
          numbered 1–40, valid answers and options, and file references.
        </p>
        {dirty && (
          <p className="text-sm text-foreground">
            Save the draft first: validation checks the saved version.
          </p>
        )}
        <Button variant="outline" onClick={() => validate.mutate()} disabled={validate.isPending}>
          {validate.isPending ? (
            <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
          ) : (
            <ListChecksIcon aria-hidden="true" />
          )}
          Run validation
        </Button>
        {validation && (
          <div aria-live="polite" className="space-y-2 rounded-lg border p-3">
            <p className={errors ? "font-medium text-destructive" : "font-medium text-success"}>
              {errors ? `${errors} error(s) block submission.` : "No blocking errors."}{" "}
              <span className="font-normal text-muted-foreground">
                {validation.length - (errors ?? 0)} warning(s).
              </span>
            </p>
            <ul className="max-h-80 space-y-1 overflow-y-auto text-sm">
              {validation.map((issue, i) => (
                <li
                  key={i}
                  className={
                    issue.severity === "error" ? "text-destructive" : "text-muted-foreground"
                  }
                >
                  <span className="font-mono text-xs">
                    {issue.location.replace(/^(listening\/common|reading\/academic) > /, "")}
                  </span>{" "}
                  — {issue.message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="space-y-3" aria-labelledby="wf-actions">
        <h3 id="wf-actions" className="font-heading text-base font-semibold">
          Workflow
        </h3>
        <div className="flex flex-wrap gap-2">
          {v.status === "draft" && can("content.edit") && (
            <ConfirmDialog
              trigger={
                <Button disabled={dirty}>
                  <SendIcon aria-hidden="true" />
                  Submit for review
                </Button>
              }
              title="Submit for review?"
              description="The test is validated at publishing strictness and then locked until a reviewer approves it or requests changes."
              confirmLabel="Submit"
              onConfirm={() => act("submit")}
            />
          )}
          {v.status === "published" && can("content.edit") && (
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  const next = await newRevision(doc.test.id);
                  apply(next, "New draft revision created from the published version.");
                  onNavigate(next.version.id);
                } catch (e) {
                  fail(e);
                }
              }}
            >
              <FilePlus2Icon aria-hidden="true" />
              Create new revision
            </Button>
          )}
          {v.approved && can("content.publish") && (
            <ConfirmDialog
              trigger={
                <Button>
                  <UploadCloudIcon aria-hidden="true" />
                  Publish
                </Button>
              }
              title="Publish this version?"
              description="It becomes the live version and can no longer be edited. A previously published version is archived."
              confirmLabel="Publish"
              onConfirm={() => act("publish")}
            />
          )}
          {v.status === "published" && can("content.publish") && (
            <ConfirmDialog
              trigger={
                <Button variant="outline">
                  <ArchiveIcon aria-hidden="true" />
                  Archive
                </Button>
              }
              title="Archive this test?"
              description="The test leaves the library. The version stays stored for history and cannot be edited."
              confirmLabel="Archive"
              destructive
              onConfirm={() => act("archive")}
            />
          )}
          {v.status === "draft" && can("content.edit") && (
            <ConfirmDialog
              trigger={
                <Button variant="ghost">
                  <Trash2Icon aria-hidden="true" />
                  Delete draft
                </Button>
              }
              title="Delete this draft?"
              description={
                doc.versions.length > 1
                  ? "Only this draft is deleted. Other versions are kept."
                  : "This test has no other versions, so the test itself is removed. This cannot be undone."
              }
              confirmLabel="Delete draft"
              destructive
              onConfirm={async () => {
                try {
                  await deleteDraft(v.id);
                  await queryClient.invalidateQueries({ queryKey: queryKeys.listening.all });
                  toast.success("Draft deleted.");
                  onDeleted();
                } catch (e) {
                  fail(e);
                }
              }}
            />
          )}
        </div>
        {v.status === "in_review" && !v.approved && !can("content.publish") && (
          <p className="text-sm text-muted-foreground">Waiting for a reviewer.</p>
        )}
        {v.approved && !can("content.publish") && (
          <p className="text-sm text-muted-foreground">
            Approved. An administrator with publishing permission can publish it.
          </p>
        )}
      </section>

      {v.status === "in_review" && can("content.review") && (
        <section className="space-y-3 rounded-lg border p-4" aria-labelledby="wf-review">
          <h3 id="wf-review" className="font-heading text-base font-semibold">
            Review
          </h3>
          {isAuthor ? (
            <p className="text-sm text-muted-foreground">
              You created this version, so another staff member must review it (four-eyes rule).
            </p>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="wf-comment">Comment (optional)</Label>
                <Textarea
                  id="wf-comment"
                  rows={2}
                  maxLength={2000}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void review("approved")}>
                  <CheckIcon aria-hidden="true" />
                  Approve
                </Button>
                <Button variant="outline" onClick={() => void review("changes_requested")}>
                  <UndoIcon aria-hidden="true" />
                  Request changes
                </Button>
              </div>
            </>
          )}
        </section>
      )}

      <section className="space-y-2" aria-labelledby="wf-history">
        <h3 id="wf-history" className="font-heading text-base font-semibold">
          History
        </h3>
        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div>
            <dt className="inline text-muted-foreground">Created by: </dt>
            <dd className="inline">{v.created_by_name ?? "—"}</dd>
          </div>
          {v.submitted_at && (
            <div>
              <dt className="inline text-muted-foreground">Submitted: </dt>
              <dd className="inline">{formatDate(v.submitted_at)}</dd>
            </div>
          )}
          {v.published_at && (
            <div>
              <dt className="inline text-muted-foreground">Published: </dt>
              <dd className="inline">{formatDate(v.published_at)}</dd>
            </div>
          )}
        </dl>
        {v.reviews.length > 0 && (
          <ul className="space-y-1 text-sm">
            {v.reviews.map((r, i) => (
              <li key={i}>
                <span className="font-medium">{r.reviewer_name ?? "Reviewer"}</span>{" "}
                {r.decision === "approved" ? "approved" : "requested changes"} ·{" "}
                {formatDate(r.created_at)}
                {r.comment && <span className="text-muted-foreground"> — “{r.comment}”</span>}
              </li>
            ))}
          </ul>
        )}
        {doc.versions.length > 1 && (
          <ul className="flex flex-wrap gap-2 text-sm" aria-label="Versions">
            {doc.versions.map((x) => (
              <li key={x.id}>
                <Link
                  href={`${base}/${x.id}`}
                  aria-current={x.id === v.id ? "page" : undefined}
                  className="rounded-md border px-2 py-1 hover:bg-muted aria-[current=page]:border-primary"
                >
                  v{x.version_no} · {x.status.replace("_", " ")}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
