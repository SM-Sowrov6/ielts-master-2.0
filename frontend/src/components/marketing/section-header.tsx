import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Eyebrow + h2 + lead paragraph used by the landing-page sections. */
export function SectionHeader({
  id,
  eyebrow,
  title,
  children,
  align = "center",
  className,
}: {
  id: string;
  eyebrow: string;
  title: string;
  children?: ReactNode;
  align?: "center" | "left";
  className?: string;
}) {
  const centered = align === "center";
  return (
    <div className={cn(centered && "mx-auto text-center", "max-w-2xl", className)}>
      <p className="text-xs font-semibold tracking-[0.14em] text-primary uppercase">{eyebrow}</p>
      <h2
        id={id}
        className="mt-3 font-heading text-3xl font-bold tracking-[-0.02em] text-balance sm:text-4xl lg:text-[2.75rem] lg:leading-[1.1]"
      >
        {title}
      </h2>
      {children && (
        <div className="mt-4 text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
          {children}
        </div>
      )}
    </div>
  );
}
