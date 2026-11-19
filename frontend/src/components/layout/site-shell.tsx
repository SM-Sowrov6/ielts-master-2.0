import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Brand } from "@/components/layout/brand";
import { footerNav } from "@/components/layout/nav-config";
import { SiteHeader } from "@/components/layout/site-header";
import { SkipLink } from "@/components/layout/skip-link";
import { SoonBadge, soonLabel } from "@/components/layout/soon-badge";
import { cn } from "@/lib/utils";

/**
 * Public (marketing/SEO) layout: sticky header (SiteHeader, client), main, footer. Server Component.
 * - `contained` (default): main content in the standard content column (status, design system).
 * - `full`: full-bleed main for the landing page; each section sets its own width.
 * No sign-in / account entry points: authentication is Phase 3b (blocked by D-13).
 */
export function SiteShell({
  children,
  layout = "contained",
}: {
  children: ReactNode;
  layout?: "contained" | "full";
}) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <SiteHeader />
      <main
        id="main-content"
        tabIndex={-1}
        className={cn(
          "w-full flex-1 focus:outline-none",
          layout === "contained" && "mx-auto max-w-[var(--container-content)] px-4 py-12 sm:px-6",
        )}
      >
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}

/**
 * Site footer: deep navy in both themes (it renders with the dark tokens via the `dark` class).
 * Brand column, then Product / Resources / Company / Legal. Pages that do not exist yet are
 * listed as plain text with their status ("Soon", "Pending approval"), never as links. No social
 * links until official accounts are confirmed.
 */
function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="dark ft-footer relative isolate overflow-hidden bg-[#050b1d] text-foreground">
      <div aria-hidden="true" className="ft-glow absolute inset-x-0 top-0 -z-10 h-80" />
      <div className="mx-auto max-w-[var(--container-wide)] px-4 pt-16 pb-10 sm:px-6 lg:px-8 lg:pt-20">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,3fr)] lg:gap-16">
          <div className="max-w-sm">
            <Brand mark />
            <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
              An intelligent IELTS preparation platform designed to help learners practise smarter,
              build confidence, and move closer to their target band score.
            </p>
            <Link
              href="/register"
              className="ft-cta mt-6 inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium"
            >
              Create your account
              <ArrowRightIcon aria-hidden="true" className="size-4" />
            </Link>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-4">
            {footerNav.map((group) => (
              <nav key={group.label} aria-label={group.label}>
                <h2 className="text-xs font-semibold tracking-[0.14em] text-foreground uppercase">
                  {group.label}
                </h2>
                <ul className="mt-4 space-y-3 text-sm">
                  {group.items.map((item) =>
                    item.href ? (
                      <li key={item.label}>
                        <Link
                          className="ft-link inline-flex items-center gap-2 rounded-sm text-muted-foreground"
                          href={item.href}
                          aria-label={item.soon ? soonLabel(item.label) : undefined}
                        >
                          <span className="ft-link-text">{item.label}</span>
                          {item.soon && <SoonBadge />}
                        </Link>
                      </li>
                    ) : (
                      <li
                        key={item.label}
                        className="flex flex-wrap items-center gap-x-2 gap-y-1 text-muted-foreground/75"
                      >
                        {item.label}
                        <span className="ft-status">
                          {item.status === "pending-approval" ? "Pending approval" : "Soon"}
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              </nav>
            ))}
          </div>
        </div>

        <div className="mt-14 flex flex-col gap-4 border-t pt-8 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
          <p>
            © {year} <span className="font-semibold text-foreground">IELTS MASTER</span>. Practise
            smarter, prepare with confidence.
          </p>
          <p className="text-xs md:text-right">
            AI-generated band scores are estimates and are not official IELTS results.
          </p>
        </div>
      </div>
    </footer>
  );
}
