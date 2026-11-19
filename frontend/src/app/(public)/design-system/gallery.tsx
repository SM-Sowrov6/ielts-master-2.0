"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { DataTable, type Column } from "@/components/patterns/data-table";
import { FormTextField } from "@/components/patterns/form-text-field";
import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4 border-t py-8">
      <h2 id={id} className="font-heading text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

const TOKENS = [
  "background",
  "foreground",
  "primary",
  "secondary",
  "muted",
  "accent",
  "destructive",
  "success",
  "warning",
  "info",
  "border",
  "input",
  "ring",
] as const;

type SampleRow = { id: string; name: string; status: string; updated: string };
const SAMPLE_ROWS: SampleRow[] = [
  { id: "1", name: "Example row A", status: "Draft", updated: "2026-11-17" },
  { id: "2", name: "Example row B", status: "Published", updated: "2026-11-16" },
];
const COLUMNS: Column<SampleRow>[] = [
  { id: "name", header: "Name", cell: (r) => r.name, isRowHeader: true },
  { id: "status", header: "Status", cell: (r) => <Badge variant="secondary">{r.status}</Badge> },
  { id: "updated", header: "Updated", cell: (r) => r.updated, align: "end" },
];

const demoSchema = z.object({
  displayName: z.string().trim().min(2, "Enter at least 2 characters."),
  notes: z.string().max(200, "Keep notes under 200 characters.").optional(),
});
type DemoValues = z.infer<typeof demoSchema>;

function DemoForm() {
  const form = useForm<DemoValues>({
    resolver: zodResolver(demoSchema),
    defaultValues: { displayName: "", notes: "" },
  });
  return (
    <form
      noValidate
      className="max-w-md space-y-4"
      onSubmit={form.handleSubmit(() =>
        toast.success("Form is valid (demo only, nothing was sent)."),
      )}
    >
      <FormTextField
        control={form.control}
        name="displayName"
        label="Display name"
        description="Shown to you only."
        autoComplete="off"
      />
      <FormTextField control={form.control} name="notes" label="Notes" multiline />
      <Button type="submit">Validate</Button>
    </form>
  );
}

export function Gallery() {
  return (
    <div>
      <Section id="tokens" title="Colour tokens">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {TOKENS.map((token) => (
            <li key={token} className="flex items-center gap-2 text-sm">
              <span
                aria-hidden="true"
                className="size-8 rounded-md border"
                style={{ background: `var(--${token})` }}
              />
              <code>--{token}</code>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="typography" title="Typography">
        <p className="font-heading text-3xl font-semibold">Heading 3xl</p>
        <p className="font-heading text-xl font-semibold">Heading xl</p>
        <p>Body text uses the sans token and scales with the browser text size.</p>
        <p className="text-sm text-muted-foreground">
          Muted small text (≥ 4.5:1 contrast in both themes).
        </p>
        <code className="font-mono text-sm">font-mono sample 0123456789</code>
      </Section>
      <Section id="buttons" title="Buttons and badges">
        <div className="flex flex-wrap gap-2">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="destructive">Destructive</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge>Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="outline">Outline</Badge>
          <Badge variant="destructive">Destructive</Badge>
        </div>
      </Section>
      <Section id="feedback" title="Feedback">
        <Alert>
          <AlertTitle>Information</AlertTitle>
          <AlertDescription>Inline, non-blocking information.</AlertDescription>
        </Alert>
        <Alert variant="destructive">
          <AlertTitle>Something needs attention</AlertTitle>
          <AlertDescription>Use for errors the user can act on.</AlertDescription>
        </Alert>
        <Button variant="outline" onClick={() => toast("Saved (demo toast)")}>
          Show toast
        </Button>
      </Section>
      <Section id="forms" title="Form (React Hook Form + Zod)">
        <DemoForm />
      </Section>
      <Section id="dialog" title="Dialog">
        <ConfirmDialog
          trigger={<Button variant="destructive">Delete example</Button>}
          title="Delete this example?"
          description="Demo only. Nothing will be deleted."
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            toast("Confirmed (demo)");
          }}
        />
      </Section>
      <Section id="table" title="Data table">
        <DataTable
          columns={COLUMNS}
          rows={SAMPLE_ROWS}
          getRowId={(r) => r.id}
          caption="Example records (static demo data)"
        />
        <DataTable
          columns={COLUMNS}
          rows={[]}
          getRowId={(r) => r.id}
          caption="Empty example"
          emptyDescription="Empty tables render the empty state."
        />
      </Section>
      <Section id="states" title="Loading, empty and error states">
        <LoadingState label="Loading example…" rows={2} />
        <EmptyState
          title="Nothing here yet"
          description="Empty state with optional action."
          headingLevel={3}
        />
        <ErrorState
          title="Could not load"
          description="Error state; never shows raw error text."
          headingLevel={3}
        />
      </Section>
    </div>
  );
}
