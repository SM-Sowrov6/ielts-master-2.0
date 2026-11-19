import { GraduationCapIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * Placeholder brand mark (brand colours decided 2026-11-18; no logo asset exists yet).
 * Decorative: the wordmark next to it carries the accessible name.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground shadow-elevation-2",
        className,
      )}
    >
      <GraduationCapIcon className="size-[1.125rem]" />
      <span className="absolute -right-0.5 -bottom-0.5 size-2.5 rounded-full border-2 border-background bg-brand-accent" />
    </span>
  );
}

/**
 * Text wordmark. `mark` adds the placeholder brand mark and the two-tone wordmark (public
 * header); without it the plain wordmark used by the app shells is unchanged.
 */
export function Brand({
  href = "/",
  suffix,
  mark = false,
}: {
  href?: string;
  suffix?: string;
  mark?: boolean;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 rounded-md font-heading text-base font-semibold tracking-tight"
    >
      {mark ? (
        <>
          <BrandMark />
          <span>
            IELTS <span className="text-primary">MASTER</span>
          </span>
        </>
      ) : (
        <span>IELTS MASTER</span>
      )}
      {suffix && (
        <span className="rounded-sm bg-primary px-1.5 py-0.5 text-xs font-medium text-primary-foreground">
          {suffix}
        </span>
      )}
    </Link>
  );
}
