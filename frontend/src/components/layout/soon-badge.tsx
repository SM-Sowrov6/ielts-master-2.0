/**
 * Visual "Soon" badge for nav items whose page is still a placeholder. Decorative: the link
 * itself carries the full accessible name via `soonLabel()` (e.g. "Library (coming soon)"),
 * because hidden helper text loses its leading space in some accessible-name implementations.
 */
export function SoonBadge() {
  return (
    <span
      aria-hidden="true"
      className="rounded-full border px-1.5 py-px text-[0.625rem] leading-4 font-semibold tracking-wide text-muted-foreground uppercase"
    >
      Soon
    </span>
  );
}

/** Accessible name for a placeholder nav item; starts with the visible label (WCAG 2.5.3). */
export function soonLabel(label: string): string {
  return `${label} (coming soon)`;
}
