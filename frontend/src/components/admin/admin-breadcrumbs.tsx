"use client";

import { ChevronRightIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { adminBreadcrumbs } from "@/components/admin/admin-nav";

export function AdminBreadcrumbs() {
  const trail = adminBreadcrumbs(usePathname());
  return (
    <nav aria-label="Breadcrumb" className="min-w-0">
      <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1;
          return (
            <li key={crumb.label} className="flex min-w-0 items-center gap-1.5">
              {index > 0 && <ChevronRightIcon className="size-3.5 shrink-0" aria-hidden="true" />}
              {last || !crumb.href ? (
                <span aria-current={last ? "page" : undefined} className="truncate text-foreground">
                  {crumb.label}
                </span>
              ) : (
                <Link href={crumb.href} className="truncate rounded-sm hover:text-foreground">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
