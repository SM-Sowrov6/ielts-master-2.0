"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircleIcon, PlusIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { DIFFICULTY_LABELS } from "@/components/admin/listening/labels";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import {
  ContentValidationError,
  createBook,
  createEdition,
  createLicence,
  createListeningTest,
  fetchBooks,
  fetchLicences,
  type Difficulty,
} from "@/lib/admin/listening-api";
import { fieldErrorsFrom, messageFor } from "@/lib/auth/api";
import { useModuleInfo } from "@/lib/admin/module";
import { queryKeys } from "@/lib/query/keys";

const CODE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,49}$/;
const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function parseTags(value: string): string[] {
  return [
    ...new Set(
      value
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    ),
  ];
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 120);
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-sm text-destructive">
      {message}
    </p>
  );
}

function NewBookDialog({
  open,
  onOpenChange,
  canManageLicences,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canManageLicences: boolean;
  onCreated: (bookId: string, editionId: string) => void;
}) {
  const queryClient = useQueryClient();
  const licences = useQuery({
    queryKey: [...queryKeys.listening.catalog(), "licences"],
    queryFn: fetchLicences,
    enabled: open,
  });
  const [licenceId, setLicenceId] = useState<string>("");
  const [newLicensor, setNewLicensor] = useState("");
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [edition, setEdition] = useState("1st edition");
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: async () => {
      let licence = licenceId;
      if (licence === "new") {
        licence = (await createLicence(newLicensor.trim())).id;
      }
      const book = await createBook({ license_id: licence, slug, title: title.trim() });
      const created = await createEdition(book.id, { label: edition.trim(), variant: "both" });
      return { bookId: book.id, editionId: created.id };
    },
    onSuccess: async ({ bookId, editionId }) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.listening.catalog() });
      onCreated(bookId, editionId);
      onOpenChange(false);
    },
    onError: (e) => setError(messageFor(e)),
  });
  const original = (licences.data ?? []).filter((l) => l.source_type === "original");
  const valid =
    title.trim() &&
    SLUG_PATTERN.test(slug) &&
    edition.trim() &&
    licenceId &&
    (licenceId !== "new" || newLicensor.trim());
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New collection</DialogTitle>
          <DialogDescription>
            Every test belongs to a book and edition under a content licence. Until content rights
            (D-04) are decided, only in-house original content should be created.
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
            <Label htmlFor="book-licence">Licence</Label>
            <Select value={licenceId} onValueChange={setLicenceId}>
              <SelectTrigger id="book-licence" className="w-full">
                <SelectValue placeholder="Choose a licence" />
              </SelectTrigger>
              <SelectContent>
                {original.map((l) => (
                  <SelectItem key={l.id} value={l.id}>
                    {l.licensor} (original)
                  </SelectItem>
                ))}
                {canManageLicences && (
                  <SelectItem value="new">New in-house original licence…</SelectItem>
                )}
              </SelectContent>
            </Select>
            {!canManageLicences && original.length === 0 && licences.isSuccess && (
              <p className="text-sm text-muted-foreground">
                No original-content licence exists yet. Ask an administrator with licence
                permissions to create one.
              </p>
            )}
          </div>
          {licenceId === "new" && (
            <div className="space-y-1.5">
              <Label htmlFor="book-licensor">Licensor (owner of the content)</Label>
              <Input
                id="book-licensor"
                value={newLicensor}
                onChange={(e) => setNewLicensor(e.target.value)}
                maxLength={200}
                placeholder="e.g. IELTS MASTER content team"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="book-title">Collection title</Label>
            <Input
              id="book-title"
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setSlug(slugify(e.target.value));
              }}
              maxLength={300}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="book-slug">URL slug</Label>
            <Input
              id="book-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              aria-describedby="book-slug-help"
              maxLength={120}
            />
            <p id="book-slug-help" className="text-xs text-muted-foreground">
              Lowercase letters, numbers and hyphens.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="book-edition">Edition</Label>
            <Input
              id="book-edition"
              value={edition}
              onChange={(e) => setEdition(e.target.value)}
              maxLength={100}
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || mutation.isPending}>
              {mutation.isPending && (
                <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
              )}
              Create collection
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function CreateTestForm({ permissions }: { permissions: readonly string[] }) {
  const router = useRouter();
  const { module, base, sectionCount, sectionNoun } = useModuleInfo();
  const queryClient = useQueryClient();
  const books = useQuery({ queryKey: queryKeys.listening.catalog(), queryFn: fetchBooks });
  const [bookId, setBookId] = useState("");
  const [editionId, setEditionId] = useState("");
  const [newBook, setNewBook] = useState(false);
  const [title, setTitle] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "">("");
  const { minutes: defaultMinutes } = useModuleInfo();
  const [minutes, setMinutes] = useState(String(defaultMinutes));
  const [variant, setVariant] = useState<"academic" | "general">("academic");
  const [tags, setTags] = useState("");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createListeningTest(
        {
          edition_id: editionId,
          code: code.trim(),
          title: title.trim(),
          description: description.trim() || null,
          difficulty: difficulty || null,
          tags: parseTags(tags),
          duration_seconds: minutes ? Math.round(Number(minutes) * 60) : null,
          admin_notes: notes.trim() || null,
          variant: module === "writing" ? variant : null,
        },
        module,
      ),
    onSuccess: async (doc) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.listening.all });
      toast.success(`Draft created. Now add the ${sectionCount} ${sectionNoun.toLowerCase()}s.`);
      router.push(`${base}/${doc.version.id}`);
    },
    onError: (e) => {
      setErrors(fieldErrorsFrom(e));
      setFormError(e instanceof ContentValidationError ? e.message : messageFor(e));
    },
  });

  function validate(): Record<string, string> {
    const next: Record<string, string> = {};
    if (!editionId) next.edition_id = "Choose a collection and edition.";
    if (!title.trim()) next.title = "Enter a title.";
    if (!CODE_PATTERN.test(code.trim()))
      next.code =
        "Use 1–50 letters, numbers, hyphens or underscores, starting with a letter or number.";
    const m = Number(minutes);
    if (minutes && (!Number.isFinite(m) || m < 1 || m > 240))
      next.duration_seconds = "Enter a duration between 1 and 240 minutes.";
    const tagList = parseTags(tags);
    if (tagList.length > 20 || tagList.some((t) => t.length > 50))
      next.tags = "Use at most 20 tags of up to 50 characters.";
    return next;
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const next = validate();
    setErrors(next);
    if (Object.keys(next).length === 0) mutation.mutate();
  }

  if (books.isPending) return <LoadingState label="Loading collections…" />;
  if (books.isError)
    return (
      <ErrorState title="Collections could not be loaded" description={messageFor(books.error)} />
    );

  const book = books.data.find((b) => b.id === bookId);
  const describedBy = (name: string) => (errors[name] ? `${name}-error` : undefined);

  return (
    <>
      <form noValidate onSubmit={onSubmit} className="space-y-6">
        <ol className="flex flex-wrap gap-2 text-sm" aria-label="Steps">
          <li
            className="rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground"
            aria-current="step"
          >
            1. Basic information
          </li>
          <li className="rounded-full border px-3 py-1 text-muted-foreground">
            2.{" "}
            {module === "reading"
              ? "Passages"
              : module === "writing"
                ? "Task 1 & Task 2"
                : module === "speaking"
                  ? "Parts 1–3"
                  : "Sections & audio"}
          </li>
          <li className="rounded-full border px-3 py-1 text-muted-foreground">
            3. {module === "writing" || module === "speaking" ? "Model answers" : "Questions"}
          </li>
          <li className="rounded-full border px-3 py-1 text-muted-foreground">
            4. Validate &amp; review
          </li>
        </ol>
        {formError && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            {formError}
          </p>
        )}
        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="font-heading text-base font-semibold">Collection</h2>
            </CardTitle>
            <CardDescription>Where this test lives in the content catalogue.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="test-book">Book / collection</Label>
              <Select
                value={bookId}
                onValueChange={(v) => {
                  setBookId(v);
                  const editions = books.data.find((b) => b.id === v)?.editions ?? [];
                  setEditionId(editions.length === 1 ? editions[0]!.id : "");
                }}
              >
                <SelectTrigger
                  id="test-book"
                  className="w-full"
                  aria-describedby={describedBy("edition_id")}
                >
                  <SelectValue
                    placeholder={books.data.length ? "Choose a collection" : "No collections yet"}
                  />
                </SelectTrigger>
                <SelectContent>
                  {books.data.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-edition">Edition</Label>
              <Select value={editionId} onValueChange={setEditionId} disabled={!book}>
                <SelectTrigger
                  id="test-edition"
                  className="w-full"
                  aria-describedby={describedBy("edition_id")}
                >
                  <SelectValue placeholder="Choose an edition" />
                </SelectTrigger>
                <SelectContent>
                  {(book?.editions ?? []).map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-2">
              <FieldError id="edition_id-error" message={errors.edition_id} />
              <Button type="button" variant="outline" size="sm" onClick={() => setNewBook(true)}>
                <PlusIcon aria-hidden="true" />
                New collection
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              <h2 className="font-heading text-base font-semibold">Basic information</h2>
            </CardTitle>
            <CardDescription>
              Title and identifier can be refined later while the test is a draft.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="test-title">Test title</Label>
              <Input
                id="test-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={300}
                aria-invalid={Boolean(errors.title)}
                aria-describedby={describedBy("title")}
              />
              <FieldError id="title-error" message={errors.title} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-code">Test identifier</Label>
              <Input
                id="test-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={50}
                placeholder="e.g. L-001"
                aria-invalid={Boolean(errors.code)}
                aria-describedby={describedBy("code")}
              />
              <FieldError id="code-error" message={errors.code} />
            </div>
            {module === "writing" && (
              <div className="space-y-1.5">
                <Label htmlFor="test-variant">Test type</Label>
                <Select
                  value={variant}
                  onValueChange={(v) => setVariant(v as "academic" | "general")}
                >
                  <SelectTrigger id="test-variant" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="academic">Academic (Task 1: report on a visual)</SelectItem>
                    <SelectItem value="general">General Training (Task 1: letter)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="test-difficulty">Difficulty</Label>
              <Select value={difficulty} onValueChange={(v) => setDifficulty(v as Difficulty)}>
                <SelectTrigger id="test-difficulty" className="w-full">
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(DIFFICULTY_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-duration">Estimated duration (minutes)</Label>
              <Input
                id="test-duration"
                type="number"
                inputMode="numeric"
                min={1}
                max={240}
                value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                aria-invalid={Boolean(errors.duration_seconds)}
                aria-describedby={describedBy("duration_seconds")}
              />
              <FieldError id="duration_seconds-error" message={errors.duration_seconds} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-tags">Tags</Label>
              <Input
                id="test-tags"
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="Comma separated"
                aria-invalid={Boolean(errors.tags)}
                aria-describedby={describedBy("tags")}
              />
              <FieldError id="tags-error" message={errors.tags} />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="test-description">Description</Label>
              <Textarea
                id="test-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={5000}
                rows={3}
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="test-notes">Internal admin notes</Label>
              <Textarea
                id="test-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={5000}
                rows={2}
                aria-describedby="test-notes-help"
              />
              <p id="test-notes-help" className="text-xs text-muted-foreground">
                Visible to staff only. Never shown to candidates.
              </p>
            </div>
          </CardContent>
        </Card>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.push(base)}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
            Create draft and continue
          </Button>
        </div>
      </form>
      {/* Outside the form: portal events bubble through the React tree. */}
      <NewBookDialog
        open={newBook}
        onOpenChange={setNewBook}
        canManageLicences={permissions.includes("content.licenses.manage")}
        onCreated={(b, e) => {
          setBookId(b);
          setEditionId(e);
        }}
      />
    </>
  );
}
