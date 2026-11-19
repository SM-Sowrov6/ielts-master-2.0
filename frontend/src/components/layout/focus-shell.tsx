import type { ReactNode } from "react";

import { SkipLink } from "@/components/layout/skip-link";

/**
 * Distraction-free layout for exam and speaking rooms (docs/PROJECT_REQUIREMENTS.md §16):
 * no site navigation, a compact top bar with slots for title / timer / actions, and an
 * optional footer slot (e.g. question navigation). The exam features themselves arrive in
 * Phase 7 (exams) and Phase 10 (speaking).
 */
export function FocusShell({
  title,
  status,
  actions,
  footer,
  fill = false,
  children,
}: {
  title: string;
  /** e.g. a server-synced timer (Phase 7). Rendered in a polite live region. */
  status?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  /** Use the whole screen: full width, exactly the viewport height, no page scroll (the content
   * scrolls inside its own panes, e.g. the Reading passage | questions split). */
  fill?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className={
        // fixed: a containing block for absolutely positioned descendants (e.g. visually hidden
        // inputs), so nothing can stretch the document and bring back a page scrollbar.
        fill ? "fixed inset-0 flex flex-col overflow-hidden" : "flex min-h-dvh flex-col"
      }
    >
      <SkipLink />
      <header className="sticky top-0 z-[var(--z-index-header)] flex h-[var(--spacing-header)] items-center gap-4 border-b bg-background px-4">
        <p className="truncate font-heading font-semibold">{title}</p>
        <div className="ml-auto flex items-center gap-3">
          {status && (
            <div aria-live="polite" className="text-sm tabular-nums">
              {status}
            </div>
          )}
          {actions}
        </div>
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className={
          fill
            ? "flex min-h-0 w-full flex-1 flex-col overflow-hidden px-4 py-3 focus:outline-none"
            : "mx-auto w-full max-w-[var(--container-content)] flex-1 px-4 py-6 focus:outline-none"
        }
      >
        {children}
      </main>
      {footer && (
        <footer
          className={
            fill
              ? "shrink-0 border-t bg-background px-4 py-2"
              : "sticky bottom-0 border-t bg-background px-4 py-3"
          }
        >
          {footer}
        </footer>
      )}
    </div>
  );
}
