"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActivePath, navSections, type NavSectionKey } from "@/components/layout/nav-config";
import { cn } from "@/lib/utils";

/** Section navigation with `aria-current="page"` on the active item. */
export function NavList({
  section,
  onNavigate,
}: {
  section: NavSectionKey;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const { items, label, rootHref } = navSections[section];
  return (
    <nav aria-label={label}>
      <ul className="flex flex-col gap-1">
        {items.map(({ href, label: itemLabel, icon: Icon }) => {
          const active = isActivePath(pathname, href, rootHref);
          return (
            <li key={href}>
              <Link
                href={href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  active && "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {itemLabel}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
