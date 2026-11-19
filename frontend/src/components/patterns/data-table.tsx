import type { ReactNode } from "react";

import { EmptyState } from "@/components/patterns/states";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

export type Column<Row> = {
  id: string;
  header: string;
  cell: (row: Row) => ReactNode;
  align?: "start" | "end";
  /** Marks the column that names the row; rendered as a row header (<th scope="row">). */
  isRowHeader?: boolean;
};

type DataTableProps<Row> = {
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  getRowId: (row: Row) => string;
  /** Required accessible name; visible caption unless `captionHidden`. */
  caption: string;
  captionHidden?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
};

/**
 * Presentational table for server-paginated data. Sorting/pagination state lives in the
 * caller (URL search params or TanStack Query); this component only renders. Columns scroll
 * horizontally on small screens instead of breaking the layout (WCAG 1.4.10).
 */
export function DataTable<Row>({
  columns,
  rows,
  getRowId,
  caption,
  captionHidden = false,
  emptyTitle = "No records yet",
  emptyDescription,
}: DataTableProps<Row>) {
  if (rows.length === 0) {
    return <EmptyState title={emptyTitle} description={emptyDescription} headingLevel={3} />;
  }
  const alignClass = (align?: "start" | "end") => (align === "end" ? "text-right" : "text-left");
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableCaption className={cn(captionHidden && "sr-only")}>{caption}</TableCaption>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead key={column.id} scope="col" className={alignClass(column.align)}>
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={getRowId(row)}>
              {columns.map((column) =>
                column.isRowHeader ? (
                  <th
                    key={column.id}
                    scope="row"
                    className={cn("p-2 font-medium", alignClass(column.align))}
                  >
                    {column.cell(row)}
                  </th>
                ) : (
                  <TableCell key={column.id} className={alignClass(column.align)}>
                    {column.cell(row)}
                  </TableCell>
                ),
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
