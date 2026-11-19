"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { adminNavGroups, isActiveAdminPath } from "@/components/admin/admin-nav";
import { SoonBadge } from "@/components/layout/soon-badge";
import { cn } from "@/lib/utils";

const itemClass =
  "flex min-h-9 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground";

/**
 * Grouped console navigation. Working pages are links (`aria-current="page"` on the active one);
 * planned modules are plain, non-focusable text with a "Soon" badge (and "(coming soon)" for
 * screen readers), so they can never be mistaken for working features.
 */
export function AdminSidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Admin navigation" className="flex flex-col gap-5">
      {adminNavGroups.map((group) => (
        <div key={group.label} className="flex flex-col gap-1">
          <h2 className="px-3 text-[0.6875rem] font-semibold tracking-wider text-muted-foreground uppercase">
            {group.label}
          </h2>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              if (item.status === "soon") {
                return (
                  <li key={item.id}>
                    <span
                      data-status="soon"
                      title={item.description}
                      className={cn(itemClass, "cursor-default text-muted-foreground")}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate">
                        {item.label}
                        <span className="sr-only"> (coming soon)</span>
                      </span>
                      <SoonBadge />
                    </span>
                  </li>
                );
              }
              const active = isActiveAdminPath(pathname, item.href);
              return (
                <li key={item.id}>
                  <Link
                    href={item.href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      itemClass,
                      "transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                      active && "bg-sidebar-accent text-sidebar-accent-foreground",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
