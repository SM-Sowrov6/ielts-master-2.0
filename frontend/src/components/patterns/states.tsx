import { AlertCircleIcon, InboxIcon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

type StateProps = {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  icon?: LucideIcon;
  className?: string;
  /** Heading level for the title, so the state fits the surrounding document outline. */
  headingLevel?: 2 | 3;
};

function StateFrame({
  title,
  description,
  action,
  icon: Icon,
  className,
  headingLevel = 2,
  tone,
  role,
}: StateProps & { icon: LucideIcon; tone: "neutral" | "error"; role?: "alert" }) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <div
      role={role}
      className={cn(
        "flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center",
        className,
      )}
    >
      <Icon
        aria-hidden="true"
        className={cn("size-10", tone === "error" ? "text-destructive" : "text-muted-foreground")}
      />
      <Heading className="font-heading text-lg font-semibold">{title}</Heading>
      {description && (
        <p className="max-w-[var(--container-prose)] text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Nothing to show yet (no data, no results, not built yet). */
export function EmptyState({ icon = InboxIcon, ...props }: StateProps) {
  return <StateFrame {...props} icon={icon} tone="neutral" />;
}

/** Something failed. Announced to assistive technology (role="alert"). Never shows raw errors. */
export function ErrorState({ icon = AlertCircleIcon, ...props }: StateProps) {
  return <StateFrame {...props} icon={icon} tone="error" role="alert" />;
}

/** Content is loading. Exposes a single status message instead of many silent skeletons. */
export function LoadingState({ label = "Loading…", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} aria-hidden="true" className="h-12 w-full" />
      ))}
    </div>
  );
}
