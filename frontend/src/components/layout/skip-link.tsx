/** First focusable element on every page: jumps keyboard users past navigation (WCAG 2.4.1). */
export function SkipLink({ targetId = "main-content" }: { targetId?: string }) {
  return (
    <a
      href={`#${targetId}`}
      className="sr-only rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[var(--z-index-overlay)]"
    >
      Skip to main content
    </a>
  );
}
