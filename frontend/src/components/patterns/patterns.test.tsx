import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { DataTable, type Column } from "@/components/patterns/data-table";
import { EmptyState, ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import { axeViolations } from "@/test/axe";

type Row = { id: string; name: string; score: number };
const columns: Column<Row>[] = [
  { id: "name", header: "Name", cell: (r) => r.name, isRowHeader: true },
  { id: "score", header: "Score", cell: (r) => r.score, align: "end" },
];

describe("state patterns", () => {
  it("error state is announced as an alert; empty state is not", async () => {
    const { container } = render(
      <>
        <EmptyState title="Nothing yet" />
        <ErrorState title="Could not load" description="Please try again." />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load");
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(2);
    expect(await axeViolations(container)).toEqual([]);
  });

  it("loading state exposes one status message for assistive technology", async () => {
    const { container } = render(<LoadingState label="Loading tests…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading tests…");
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("DataTable", () => {
  it("renders a captioned table with column and row headers", async () => {
    const { container } = render(
      <DataTable
        columns={columns}
        rows={[{ id: "1", name: "Alice", score: 7 }]}
        getRowId={(r) => r.id}
        caption="Scores"
      />,
    );
    const table = screen.getByRole("table", { name: "Scores" });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Name",
      "Score",
    ]);
    expect(screen.getByRole("rowheader", { name: "Alice" })).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("renders the empty state instead of an empty table", () => {
    render(
      <DataTable
        columns={columns}
        rows={[]}
        getRowId={(r) => r.id}
        caption="Scores"
        emptyTitle="No scores yet"
      />,
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No scores yet" })).toBeInTheDocument();
  });
});

describe("ConfirmDialog", () => {
  it("is keyboard operable: opens, traps focus, Esc cancels and focus returns to the trigger", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        trigger={<Button>Publish</Button>}
        title="Publish test?"
        description="Students will see it."
        confirmLabel="Publish now"
        onConfirm={onConfirm}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Publish" });
    trigger.focus();
    await user.keyboard("{Enter}");
    const dialog = await screen.findByRole("dialog", { name: "Publish test?" });
    expect(dialog).toHaveAccessibleDescription("Students will see it.");
    expect(await axeViolations(document.body)).toEqual([]);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("awaits async confirmation before closing", async () => {
    const user = userEvent.setup();
    let resolve: () => void = () => undefined;
    const onConfirm = vi.fn(() => new Promise<void>((r) => (resolve = r)));
    render(
      <ConfirmDialog
        trigger={<Button>Delete</Button>}
        title="Delete?"
        description="Cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onConfirm}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const confirm = within(await screen.findByRole("dialog")).getByRole("button", {
      name: "Delete",
    });
    await user.click(confirm);
    expect(confirm).toBeDisabled();
    resolve();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
