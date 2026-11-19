import { AlertCircleIcon, CheckCircle2Icon, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/** Form-level error (role="alert", announced when it appears). */
export function FormError({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <Alert variant="destructive" className="border-destructive/40 bg-destructive/5 px-3 py-2.5">
      <AlertCircleIcon aria-hidden="true" />
      {title && <AlertTitle>{title}</AlertTitle>}
      {children && <AlertDescription>{children}</AlertDescription>}
    </Alert>
  );
}

/** Result panel shown in place of a form (real server outcomes only, never optimistic). */
export function ResultPanel({
  icon: Icon = CheckCircle2Icon,
  tone = "success",
  title,
  children,
  actions,
}: {
  icon?: LucideIcon;
  tone?: "success" | "neutral" | "error";
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  const toneClass = {
    success: "bg-success/10 text-success",
    neutral: "bg-accent text-accent-foreground",
    error: "bg-destructive/10 text-destructive",
  }[tone];
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      <span className={`grid size-12 place-items-center rounded-xl ${toneClass}`}>
        <Icon className="size-6" aria-hidden="true" />
      </span>
      <div className="space-y-2">
        <h1 className="font-heading text-2xl font-bold tracking-tight">{title}</h1>
        <div className="space-y-2 text-sm leading-relaxed text-muted-foreground">{children}</div>
      </div>
      {actions && <div className="flex flex-col gap-3">{actions}</div>}
    </div>
  );
}

export function AuthHeading({ title, description }: { title: string; description: ReactNode }) {
  return (
    <div className="space-y-2">
      <h1 className="font-heading text-2xl font-bold tracking-tight sm:text-[1.75rem]">{title}</h1>
      <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
    </div>
  );
}
