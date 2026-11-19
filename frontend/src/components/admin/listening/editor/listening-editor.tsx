"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  EyeIcon,
  LoaderCircleIcon,
  LockIcon,
  SaveIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  draftFromDocument,
  saveBody,
  sectionRange,
  type DraftState,
} from "@/components/admin/listening/editor/model";
import { IssueList } from "@/components/admin/listening/editor/question-editor";
import { SectionEditor } from "@/components/admin/listening/editor/section-editor";
import { WorkflowPanel } from "@/components/admin/listening/editor/workflow-panel";
import {
  DIFFICULTY_LABELS,
  QUESTION_TYPES,
  StatusBadge,
} from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { countErrors, issueTarget, requestErrorsToIssues } from "@/lib/admin/issues";
import {
  ContentValidationError,
  fetchEditorDocument,
  fetchQuestionTypes,
  saveDraft,
  type Asset,
  type Difficulty,
  type EditorDocument,
  type Issue,
} from "@/lib/admin/listening-api";
import { ApiError } from "@/lib/api/errors";
import type { Me } from "@/lib/auth/api";
import { messageFor } from "@/lib/auth/api";
import { useModuleInfo, type ObjectiveModule } from "@/lib/admin/module";
import { queryKeys } from "@/lib/query/keys";
import { cn } from "@/lib/utils";

type Step = "details" | 1 | 2 | 3 | 4 | "review";

function versionStatus(doc: EditorDocument) {
  return doc.version.approved ? "approved" : doc.version.status;
}

function Details({
  draft,
  readOnly,
  issues,
  onChange,
}: {
  draft: DraftState;
  readOnly: boolean;
  issues: readonly Issue[];
  onChange: (patch: Partial<DraftState>) => void;
}) {
  const testIssues = issues.filter((i) => i.location === "test" || i.location === "licence");
  return (
    <div className="space-y-4">
      <h2 className="font-heading text-xl font-semibold">Basic information</h2>
      <IssueList issues={testIssues} />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor="ed-title">Test title</Label>
          <Input
            id="ed-title"
            value={draft.title}
            readOnly={readOnly}
            maxLength={300}
            onChange={(e) => onChange({ title: e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ed-difficulty">Difficulty</Label>
          <Select
            value={draft.difficulty || "none"}
            disabled={readOnly}
            onValueChange={(v) => onChange({ difficulty: v === "none" ? "" : (v as Difficulty) })}
          >
            <SelectTrigger id="ed-difficulty" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Not set</SelectItem>
              {Object.entries(DIFFICULTY_LABELS).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ed-minutes">Estimated duration (minutes)</Label>
          <Input
            id="ed-minutes"
            type="number"
            min={1}
            max={240}
            value={draft.minutes}
            readOnly={readOnly}
            onChange={(e) => onChange({ minutes: e.target.value })}
          />
        </div>
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor="ed-tags">Tags</Label>
          <Input
            id="ed-tags"
            value={draft.tags}
            readOnly={readOnly}
            placeholder="Comma separated"
            onChange={(e) => onChange({ tags: e.target.value })}
          />
        </div>
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor="ed-description">Description</Label>
          <Textarea
            id="ed-description"
            rows={3}
            value={draft.description}
            readOnly={readOnly}
            maxLength={5000}
            onChange={(e) => onChange({ description: e.target.value })}
          />
        </div>
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor="ed-notes">Internal admin notes</Label>
          <Textarea
            id="ed-notes"
            rows={2}
            value={draft.adminNotes}
            readOnly={readOnly}
            maxLength={5000}
            onChange={(e) => onChange({ adminNotes: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">Staff only; never shown to candidates.</p>
        </div>
        <div className="space-y-1.5 lg:col-span-2">
          <Label htmlFor="ed-change">Change note for reviewers</Label>
          <Input
            id="ed-change"
            value={draft.changeNote}
            readOnly={readOnly}
            maxLength={2000}
            onChange={(e) => onChange({ changeNote: e.target.value })}
          />
        </div>
      </div>
    </div>
  );
}

export function ListeningEditor({ versionId, user }: { versionId: string; user: Me }) {
  const router = useRouter();
  const { module, base, title, sectionNoun } = useModuleInfo();
  const queryClient = useQueryClient();
  const canEdit = user.permissions.includes("content.edit");
  const doc = useQuery({
    queryKey: queryKeys.listening.document(versionId),
    queryFn: () => fetchEditorDocument(versionId),
  });
  const types = useQuery({
    queryKey: [...queryKeys.listening.questionTypes(), module],
    queryFn: () => fetchQuestionTypes(module as ObjectiveModule),
    staleTime: Infinity,
  });
  const [draft, setDraft] = useState<DraftState | null>(null);
  const [baseline, setBaseline] = useState<string>("");
  const [loadedRevision, setLoadedRevision] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [step, setStep] = useState<Step>("details");
  const [extraAssets, setExtraAssets] = useState<Asset[]>([]);

  const dirty = draft !== null && JSON.stringify(draft) !== baseline;
  // (Re)initialise local state when a new server revision arrives, but never over unsaved edits:
  // those keep their loaded revision, so saving them reports the conflict instead of overwriting.
  const remoteRevision = doc.data?.version.revision ?? null;
  const backupKey = `content-draft:${versionId}`;
  if (doc.data && remoteRevision !== loadedRevision && !dirty) {
    const next = draftFromDocument(doc.data);
    // Unsaved edits kept in this browser for the same server revision (e.g. a save failed with
    // validation errors and the page was left): restore them instead of losing the work.
    let backup: DraftState | null = null;
    try {
      const raw = localStorage.getItem(backupKey);
      const parsed = raw ? (JSON.parse(raw) as { revision: string; draft: DraftState }) : null;
      if (parsed && parsed.revision === remoteRevision) backup = parsed.draft;
    } catch {
      backup = null;
    }
    setDraft(backup ?? next);
    setBaseline(JSON.stringify(next));
    setLoadedRevision(remoteRevision);
    setRestored(backup !== null && JSON.stringify(backup) !== JSON.stringify(next));
  }
  const changedElsewhere = dirty && remoteRevision !== null && remoteRevision !== loadedRevision;
  useEffect(() => {
    try {
      if (dirty && draft && loadedRevision)
        localStorage.setItem(backupKey, JSON.stringify({ revision: loadedRevision, draft }));
      else if (!dirty) localStorage.removeItem(backupKey);
    } catch {
      /* storage unavailable: the beforeunload warning still applies */
    }
  }, [dirty, draft, loadedRevision, backupKey]);
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
    mutationFn: () => saveDraft(versionId, saveBody(doc.data!, draft!, loadedRevision!)),
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
        toast.error(
          `Not saved: ${countErrors(e.issues)} error(s) need fixing. See the highlighted fields.`,
        );
      } else if (e instanceof ApiError && e.code === "validation_error" && e.fieldErrors?.length) {
        const mapped = requestErrorsToIssues(e.fieldErrors, draft?.sections ?? []);
        setIssues(mapped);
        toast.error(
          `Not saved: ${mapped.length} field(s) are incomplete. See the highlighted sections and questions.`,
        );
      } else if (e instanceof ApiError && e.code === "content_draft_conflict") {
        toast.error(
          "Someone else saved this draft. Reload to get the latest version (your changes are kept on screen until then).",
        );
      } else {
        toast.error(messageFor(e));
      }
    },
  });

  if (doc.isPending || !draft) return <LoadingState label="Loading test…" />;
  if (doc.isError) {
    return (
      <ErrorState
        title={
          doc.error instanceof ApiError && doc.error.status === 404
            ? "Test version not found"
            : "The test could not be loaded"
        }
        description={messageFor(doc.error)}
        action={
          <Button asChild variant="outline">
            <Link href={base}>Back to {title} Management</Link>
          </Button>
        }
      />
    );
  }

  const d = doc.data;
  const readOnly = !canEdit || d.version.status !== "draft";
  const listeningTypes = (types.data ?? []).map((t) => t.code).filter((c) => c in QUESTION_TYPES);
  const shared = {
    testId: d.test.id,
    assets,
    readOnly,
    issues,
    allSections: draft.sections,
    onAsset: (a: Asset) => setExtraAssets((list) => [...list, a]),
    types: listeningTypes.length ? listeningTypes : Object.keys(QUESTION_TYPES),
  };
  const steps: { key: Step; label: string; hint?: string; errors: number }[] = [
    {
      key: "details",
      label: "Details",
      errors: countErrors(issues.filter((i) => i.location === "test" || i.location === "licence")),
    },
    ...draft.sections.map((s) => ({
      key: s.section_no as Step,
      label: `${sectionNoun} ${s.section_no}`,
      hint: sectionRange(s),
      errors: countErrors(issues.filter((i) => issueTarget(i.location).section === s.section_no)),
    })),
    { key: "review", label: "Validate & review", errors: 0 },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
              {d.test.title}
            </h1>
            <StatusBadge status={versionStatus(d)} />
          </div>
          <p className="text-sm text-muted-foreground">
            {d.test.code} · version {d.version.version_no} · {d.catalog.book_title} (
            {d.catalog.edition_label})
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link
              href={`${base}/${versionId}/preview`}
              onClick={(e) => {
                if (!dirty) return;
                e.preventDefault();
                toast.warning(
                  "You have unsaved changes. Save the draft (and fix any errors) before previewing.",
                );
              }}
            >
              <EyeIcon aria-hidden="true" />
              Preview
            </Link>
          </Button>
          {!readOnly && (
            <Button onClick={() => save.mutate()} disabled={save.isPending || !dirty}>
              {save.isPending ? (
                <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
              ) : (
                <SaveIcon aria-hidden="true" />
              )}
              {dirty ? "Save draft" : "Saved"}
            </Button>
          )}
        </div>
      </div>
      {readOnly && (
        <p className="flex items-start gap-2 rounded-lg border bg-muted/50 px-4 py-3 text-sm">
          <LockIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {!canEdit
            ? "Your role can view this test but not edit it."
            : d.version.status === "in_review"
              ? "This version is in review and locked. A reviewer can approve it or request changes."
              : "Published and archived versions are immutable. Create a new revision to make changes."}
        </p>
      )}
      {restored && dirty && (
        <p role="status" className="rounded-lg border border-info/40 bg-info/10 px-4 py-3 text-sm">
          Unsaved changes from your last visit were restored from this browser. Save the draft to
          keep them.
        </p>
      )}
      {changedElsewhere && (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
        >
          <AlertTriangleIcon className="size-4 shrink-0 text-destructive" aria-hidden="true" />
          Someone else changed this test since you opened it. Your edits are kept on screen, but
          saving will be refused. Copy what you need, then reload the page.
        </p>
      )}
      {dirty && !readOnly && (
        <p role="status" className="flex items-center gap-2 text-sm text-foreground">
          <AlertTriangleIcon className="size-4 text-warning" aria-hidden="true" />
          Unsaved changes. Uploaded files are attached only when you save the draft.
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav aria-label="Editor steps">
          <ol className="flex gap-2 overflow-x-auto lg:flex-col">
            {steps.map((s) => (
              <li key={String(s.key)} className="shrink-0">
                <button
                  type="button"
                  onClick={() => setStep(s.key)}
                  aria-current={step === s.key ? "step" : undefined}
                  aria-label={[
                    s.label,
                    s.errors ? `${s.errors} ${s.errors === 1 ? "error" : "errors"}` : null,
                    s.hint,
                  ]
                    .filter(Boolean)
                    .join(", ")}
                  className={cn(
                    "flex w-full flex-col rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                    step === s.key && "border-primary bg-primary/5",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    {s.label}
                    {s.errors > 0 ? (
                      <span className="rounded-full bg-destructive/10 px-1.5 text-xs text-destructive">
                        {s.errors}
                      </span>
                    ) : null}
                  </span>
                  {s.hint && <span className="text-xs text-muted-foreground">{s.hint}</span>}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <Card>
          <CardContent className="py-2">
            {step === "details" && (
              <Details
                draft={draft}
                readOnly={readOnly}
                issues={issues}
                onChange={(patch) => setDraft({ ...draft, ...patch })}
              />
            )}
            {typeof step === "number" && (
              <SectionEditor
                section={draft.sections[step - 1]!}
                shared={shared}
                onChange={(section) =>
                  setDraft({
                    ...draft,
                    sections: draft.sections.map((s) =>
                      s.section_no === section.section_no ? section : s,
                    ),
                  })
                }
              />
            )}
            {step === "review" && (
              <WorkflowPanel
                doc={d}
                user={user}
                dirty={dirty}
                onIssues={setIssues}
                onDeleted={() => router.push(base)}
                onNavigate={(id) => router.push(`${base}/${id}`)}
              />
            )}
          </CardContent>
        </Card>
      </div>
      {issues.length > 0 && step !== "review" && countErrors(issues) === 0 && (
        <p className="flex items-center gap-2 text-sm text-success">
          <CheckCircle2Icon className="size-4" aria-hidden="true" />
          No blocking issues at the last save.
        </p>
      )}
    </div>
  );
}
