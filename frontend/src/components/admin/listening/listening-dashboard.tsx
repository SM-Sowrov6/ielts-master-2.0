"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArchiveIcon,
  CopyIcon,
  EyeIcon,
  HeadphonesIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  SearchIcon,
  SendIcon,
  UploadCloudIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  DIFFICULTY_LABELS,
  STATUS_LABELS,
  StatusBadge,
  formatDate,
  formatDuration,
} from "@/components/admin/listening/labels";
import { DataTable, type Column } from "@/components/patterns/data-table";
import { PageHeader } from "@/components/patterns/page-header";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  duplicateTest,
  fetchListeningOverview,
  fetchListeningTests,
  runAction,
  type Difficulty,
  type ListStatus,
  type ListeningRow,
} from "@/lib/admin/listening-api";
import { messageFor } from "@/lib/auth/api";
import { useModuleInfo } from "@/lib/admin/module";
import { queryKeys } from "@/lib/query/keys";

const PAGE_SIZE = 10;
const ALL = "all";

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3 shadow-elevation-1">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-heading text-2xl font-semibold tabular-nums">
        {value === undefined ? "—" : value}
      </dd>
    </div>
  );
}

function DuplicateDialog({ row, onClose }: { row: ListeningRow | null; onClose: () => void }) {
  const router = useRouter();
  const { base } = useModuleInfo();
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => duplicateTest(row!.version_id, code.trim(), title.trim()),
    onSuccess: async (doc) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.listening.all });
      toast.success("Copy created as a new draft.");
      onClose();
      router.push(`${base}/${doc.version.id}`);
    },
    onError: (e) => setError(messageFor(e)),
  });
  return (
    <Dialog
      open={row !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
        else {
          setCode(`${row?.code ?? ""}-copy`);
          setTitle(`${row?.title ?? ""} (copy)`);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Duplicate test</DialogTitle>
          <DialogDescription>
            Creates a new draft test in the same edition with a copy of all sections, questions and
            audio references. The original is not changed.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setError(null);
            mutation.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="dup-code">New test identifier</Label>
            <Input
              id="dup-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              maxLength={50}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dup-title">New title</Label>
            <Input
              id="dup-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={300}
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending || !code.trim() || !title.trim()}>
              Duplicate
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RowActions({
  row,
  canEdit,
  canPublish,
  onDuplicate,
  onConfirm,
}: {
  row: ListeningRow;
  canEdit: boolean;
  canPublish: boolean;
  onDuplicate: () => void;
  onConfirm: (kind: "submit" | "publish" | "archive") => void;
}) {
  const { base } = useModuleInfo();
  const editable = row.status === "draft";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Actions for ${row.title}`}>
          <MoreHorizontalIcon aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="truncate">{row.code}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href={`${base}/${row.version_id}`}>
            {editable && canEdit ? (
              <PencilIcon aria-hidden="true" />
            ) : (
              <EyeIcon aria-hidden="true" />
            )}
            {editable && canEdit ? "Edit" : "View"}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href={`${base}/${row.version_id}/preview`}>
            <HeadphonesIcon aria-hidden="true" />
            Preview
          </Link>
        </DropdownMenuItem>
        {canEdit && (
          <DropdownMenuItem onSelect={onDuplicate}>
            <CopyIcon aria-hidden="true" />
            Duplicate
          </DropdownMenuItem>
        )}
        {canEdit && editable && (
          <DropdownMenuItem onSelect={() => onConfirm("submit")}>
            <SendIcon aria-hidden="true" />
            Submit for review
          </DropdownMenuItem>
        )}
        {canPublish && row.status === "approved" && (
          <DropdownMenuItem onSelect={() => onConfirm("publish")}>
            <UploadCloudIcon aria-hidden="true" />
            Publish
          </DropdownMenuItem>
        )}
        {canPublish && row.status === "published" && (
          <DropdownMenuItem variant="destructive" onSelect={() => onConfirm("archive")}>
            <ArchiveIcon aria-hidden="true" />
            Archive
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const CONFIRM_COPY = {
  submit: {
    title: "Submit for review?",
    body: "The test is validated at publishing strictness. If it passes, it is locked for editing until a reviewer approves it or requests changes.",
    action: "Submit for review",
  },
  publish: {
    title: "Publish this test?",
    body: "The approved version becomes the live version and can no longer be edited. Any previously published version is archived.",
    action: "Publish",
  },
  archive: {
    title: "Archive this test?",
    body: "The test leaves the library. The version stays stored and readable for history; it cannot be edited or deleted.",
    action: "Archive",
  },
} as const;

export function ListeningDashboard({ permissions }: { permissions: readonly string[] }) {
  const { module, base, title } = useModuleInfo();
  const canEdit = permissions.includes("content.edit");
  const canPublish = permissions.includes("content.publish");
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [status, setStatus] = useState<ListStatus | typeof ALL>(ALL);
  const [difficulty, setDifficulty] = useState<Difficulty | typeof ALL>(ALL);
  const [page, setPage] = useState(0);
  const [duplicating, setDuplicating] = useState<ListeningRow | null>(null);
  const [confirming, setConfirming] = useState<{
    row: ListeningRow;
    kind: "submit" | "publish" | "archive";
  } | null>(null);

  const query = {
    search: submittedSearch || undefined,
    status: status === ALL ? undefined : status,
    difficulty: difficulty === ALL ? undefined : difficulty,
    offset: page * PAGE_SIZE,
    limit: PAGE_SIZE,
  };
  const overview = useQuery({
    queryKey: [...queryKeys.listening.overview(), module],
    queryFn: () => fetchListeningOverview(module),
  });
  const list = useQuery({
    queryKey: queryKeys.listening.list({ ...query, module }),
    queryFn: () => fetchListeningTests(query, module),
    placeholderData: keepPreviousData,
  });
  const action = useMutation({
    mutationFn: (c: { row: ListeningRow; kind: "submit" | "publish" | "archive" }) =>
      runAction(c.row.version_id, c.kind),
    onSuccess: async (_doc, c) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.listening.all });
      toast.success(
        { submit: "Submitted for review.", publish: "Published.", archive: "Archived." }[c.kind],
      );
      setConfirming(null);
    },
    onError: (e) => {
      toast.error(messageFor(e));
      setConfirming(null);
    },
  });

  const columns: Column<ListeningRow>[] = [
    {
      id: "title",
      header: "Test",
      isRowHeader: true,
      cell: (r) => (
        <div className="min-w-[12rem]">
          <Link
            href={`${base}/${r.version_id}`}
            className="font-medium underline-offset-4 hover:underline"
          >
            {r.title}
          </Link>
          <p className="text-xs font-normal text-muted-foreground">
            {r.code} · v{r.version_no} · {r.book_title}
          </p>
        </div>
      ),
    },
    {
      id: "difficulty",
      header: "Difficulty",
      cell: (r) => (r.difficulty ? DIFFICULTY_LABELS[r.difficulty] : "—"),
    },
    { id: "sections", header: "Sections", align: "end", cell: (r) => r.sections },
    { id: "questions", header: "Questions", align: "end", cell: (r) => r.questions },
    { id: "duration", header: "Duration", cell: (r) => formatDuration(r.duration_seconds) },
    {
      id: "status",
      header: "Status",
      cell: (r) => (
        <div className="flex flex-col items-start gap-1">
          <StatusBadge status={r.status} />
          {r.live_version_id && r.live_version_id !== r.version_id && (
            <span className="text-xs text-muted-foreground">Live version published</span>
          )}
        </div>
      ),
    },
    {
      id: "updated",
      header: "Last updated",
      cell: (r) => <span className="whitespace-nowrap text-xs">{formatDate(r.updated_at)}</span>,
    },
    { id: "author", header: "Created by", cell: (r) => r.created_by_name ?? "—" },
    {
      id: "actions",
      header: "Actions",
      align: "end",
      cell: (r) => (
        <RowActions
          row={r}
          canEdit={canEdit}
          canPublish={canPublish}
          onDuplicate={() => setDuplicating(r)}
          onConfirm={(kind) => setConfirming({ row: r, kind })}
        />
      ),
    },
  ];

  const total = list.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = Boolean(submittedSearch) || status !== ALL || difficulty !== ALL;
  const o = overview.data;

  return (
    <>
      <PageHeader
        title={`${title} Management`}
        description={`Create, validate, review and publish IELTS ${title} tests. Published tests are stored centrally for the candidate ${title} module.`}
        actions={
          canEdit ? (
            <Button asChild>
              <Link href={`${base}/new`}>
                <PlusIcon aria-hidden="true" />
                New {title} test
              </Link>
            </Button>
          ) : undefined
        }
      />
      <section aria-labelledby="listening-stats" className="mb-6">
        <h2 id="listening-stats" className="sr-only">
          Overview
        </h2>
        {overview.isError ? (
          <ErrorState
            title="Statistics could not be loaded"
            description={messageFor(overview.error)}
            headingLevel={3}
          />
        ) : (
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Total tests" value={o?.total} />
            <Stat label="Published" value={o?.published} />
            <Stat label="Drafts" value={o?.draft} />
            <Stat label="Awaiting review" value={o?.in_review} />
            <Stat label="Approved" value={o?.approved} />
            <Stat label="Archived" value={o?.archived} />
          </dl>
        )}
      </section>

      <section aria-labelledby="listening-tests" className="space-y-4">
        <h2 id="listening-tests" className="sr-only">
          Listening tests
        </h2>
        <form
          role="search"
          className="flex flex-col gap-3 lg:flex-row lg:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(0);
            setSubmittedSearch(search.trim());
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor="listening-search">Search</Label>
            <div className="flex gap-2">
              <Input
                id="listening-search"
                type="search"
                placeholder="Title or identifier"
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
          <div className="grid grid-cols-2 gap-3 lg:w-[24rem]">
            <div className="space-y-1.5">
              <Label htmlFor="listening-status">Status</Label>
              <Select
                value={status}
                onValueChange={(v) => {
                  setPage(0);
                  setStatus(v as ListStatus | typeof ALL);
                }}
              >
                <SelectTrigger id="listening-status" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All statuses</SelectItem>
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="listening-difficulty">Difficulty</Label>
              <Select
                value={difficulty}
                onValueChange={(v) => {
                  setPage(0);
                  setDifficulty(v as Difficulty | typeof ALL);
                }}
              >
                <SelectTrigger id="listening-difficulty" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All levels</SelectItem>
                  {Object.entries(DIFFICULTY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </form>

        {list.isPending ? (
          <LoadingState label="Loading tests…" rows={4} />
        ) : list.isError ? (
          <ErrorState
            title="Tests could not be loaded"
            description={messageFor(list.error)}
            headingLevel={3}
            action={<Button onClick={() => void list.refetch()}>Try again</Button>}
          />
        ) : (
          <>
            <DataTable
              columns={columns}
              rows={list.data.items}
              getRowId={(r) => r.version_id}
              caption="Listening tests"
              captionHidden
              emptyTitle={filtered ? "No tests match these filters" : `No ${title} tests yet`}
              emptyDescription={
                filtered
                  ? "Change the search or filters to see more tests."
                  : canEdit
                    ? `Create the first ${title} test to start building content.`
                    : "Tests appear here once a content editor creates them."
              }
            />
            {total > 0 && (
              <nav
                aria-label="Pagination"
                className="flex flex-col items-center justify-between gap-3 text-sm sm:flex-row"
              >
                <p className="text-muted-foreground" aria-live="polite">
                  Showing {list.data.offset + 1}–
                  {Math.min(list.data.offset + list.data.items.length, total)} of {total}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                  >
                    Previous
                  </Button>
                  <span className="tabular-nums">
                    Page {page + 1} of {pages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => p + 1)}
                    disabled={page + 1 >= pages}
                  >
                    Next
                  </Button>
                </div>
              </nav>
            )}
          </>
        )}
      </section>

      <DuplicateDialog row={duplicating} onClose={() => setDuplicating(null)} />
      <Dialog open={confirming !== null} onOpenChange={(open) => !open && setConfirming(null)}>
        <DialogContent showCloseButton={false}>
          {confirming && (
            <>
              <DialogHeader>
                <DialogTitle>{CONFIRM_COPY[confirming.kind].title}</DialogTitle>
                <DialogDescription>
                  <strong className="text-foreground">{confirming.row.title}</strong> —{" "}
                  {CONFIRM_COPY[confirming.kind].body}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setConfirming(null)}
                  disabled={action.isPending}
                >
                  Cancel
                </Button>
                <Button
                  variant={confirming.kind === "archive" ? "destructive" : "default"}
                  disabled={action.isPending}
                  onClick={() => action.mutate(confirming)}
                >
                  {CONFIRM_COPY[confirming.kind].action}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
