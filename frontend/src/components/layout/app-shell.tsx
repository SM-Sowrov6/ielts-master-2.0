import type { ReactNode } from "react";

import { AccountActions } from "@/components/layout/account-actions";
import { Brand } from "@/components/layout/brand";
import { MobileNav } from "@/components/layout/mobile-nav";
import { navSections, type NavSectionKey } from "@/components/layout/nav-config";
import { NavList } from "@/components/layout/nav-list";
import { SkipLink } from "@/components/layout/skip-link";
import { ThemeToggle } from "@/components/layout/theme-toggle";

/**
 * Authenticated-area layout (student and admin variants): persistent sidebar from `lg`,
 * drawer below it. The account menu shows the signed-in user (display only; pages verify the
 * session server-side via components/auth/gates.tsx).
 */
export function AppShell({ variant, children }: { variant: NavSectionKey; children: ReactNode }) {
  const { rootHref, badge } = navSections[variant];
  return (
    <div className="flex min-h-dvh" data-shell={variant}>
      <SkipLink />
      <aside className="sticky top-0 hidden h-dvh w-[var(--spacing-sidebar)] shrink-0 flex-col gap-6 border-r border-sidebar-border bg-sidebar p-4 lg:flex">
        <Brand href={rootHref} suffix={badge} />
        <NavList section={variant} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-[var(--z-index-header)] flex h-[var(--spacing-header)] items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
          <MobileNav section={variant} />
          <div className="lg:hidden">
            <Brand href={rootHref} suffix={badge} />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <AccountActions />
          </div>
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className="mx-auto w-full max-w-[var(--container-content)] flex-1 px-4 py-8 focus:outline-none sm:px-6"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
