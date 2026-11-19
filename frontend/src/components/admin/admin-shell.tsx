import type { ReactNode } from "react";

import { AdminAccountMenu } from "@/components/admin/admin-account-menu";
import { AdminBreadcrumbs } from "@/components/admin/admin-breadcrumbs";
import { AdminMobileNav } from "@/components/admin/admin-mobile-nav";
import { ADMIN_ROOT } from "@/components/admin/admin-nav";
import { AdminSidebarNav } from "@/components/admin/admin-sidebar-nav";
import { Brand } from "@/components/layout/brand";
import { SkipLink } from "@/components/layout/skip-link";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import type { Me } from "@/lib/auth/api";

/**
 * Super Admin console layout, separate from the student shell: grouped sidebar from `lg`
 * (drawer below it), a top bar with breadcrumbs, theme toggle and the administrator's account
 * menu. Rendered only after the server has verified the staff session (app/(admin)/admin/layout).
 */
export function AdminShell({ user, children }: { user: Me; children: ReactNode }) {
  return (
    <div className="flex min-h-dvh bg-muted/30" data-shell="admin">
      <SkipLink />
      <aside className="sticky top-0 hidden h-dvh w-[var(--spacing-sidebar)] shrink-0 flex-col gap-6 overflow-y-auto border-r border-sidebar-border bg-sidebar p-4 lg:flex">
        <Brand href={ADMIN_ROOT} suffix="Admin" mark />
        <AdminSidebarNav />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-[var(--z-index-header)] flex h-[var(--spacing-header)] items-center gap-3 border-b bg-background/95 px-4 backdrop-blur sm:px-6">
          <AdminMobileNav />
          <div className="hidden min-w-0 sm:block">
            <AdminBreadcrumbs />
          </div>
          <div className="min-w-0 sm:hidden">
            <Brand href={ADMIN_ROOT} suffix="Admin" />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <ThemeToggle />
            <AdminAccountMenu user={user} />
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
