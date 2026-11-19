import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Decorative product-interface frame for landing-page illustrations. Server Component.
 * Contents are pictures of the UI, built from divs and spans only: never real buttons, inputs or
 * links. Callers place it inside an `aria-hidden` + `inert` container (see DecorativePreview).
 */
export function ProductWindow({
  title,
  meta,
  children,
  className,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "surface-sheen overflow-hidden rounded-xl border bg-card text-card-foreground shadow-elevation-float",
        className,
      )}
    >
      <div className="flex h-9 items-center gap-3 border-b bg-surface px-3.5">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
        </div>
        <span className="truncate text-xs font-medium text-muted-foreground">{title}</span>
        {meta && <div className="ml-auto flex shrink-0 items-center gap-2">{meta}</div>}
      </div>
      {children}
    </div>
  );
}

/**
 * Wrapper that removes an illustration from the accessibility tree and from keyboard focus.
 * Pair it with a short `sr-only` description where the picture carries meaning.
 */
export function DecorativePreview({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div aria-hidden="true" inert data-decorative="" className={cn("select-none", className)}>
      {children}
    </div>
  );
}
