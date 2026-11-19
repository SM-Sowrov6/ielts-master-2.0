import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";

import { soonLabel } from "@/components/layout/soon-badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Landing-page call to action for an area that is not available yet: a real link to its
 * (placeholder) route, visibly marked "Soon" and announced as "(coming soon)".
 */
export function SoonCta({
  href,
  label,
  className,
}: {
  href: string;
  label: string;
  className?: string;
}) {
  return (
    <Button
      asChild
      className={cn(
        "group h-11 px-5 text-[0.9375rem] shadow-elevation-2 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-elevation-float",
        className,
      )}
    >
      <Link href={href} aria-label={soonLabel(label)}>
        {label}
        <span className="rounded-full bg-primary-foreground/20 px-1.5 py-px text-[0.625rem] font-semibold tracking-wide uppercase">
          Soon
        </span>
        <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
      </Link>
    </Button>
  );
}
