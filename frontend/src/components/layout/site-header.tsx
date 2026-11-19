"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AccountActions } from "@/components/layout/account-actions";
import { Brand } from "@/components/layout/brand";
import { isActivePath } from "@/components/layout/nav-config";
import { SiteMobileNav } from "@/components/layout/site-mobile-nav";
import { SoonBadge, soonLabel } from "@/components/layout/soon-badge";
import { useSiteNav } from "@/components/layout/use-site-nav";
import { ThemeToggle } from "@/components/layout/theme-toggle";

/**
 * Public sticky header. Transparent over the page at the top; once the page scrolls it gains a
 * translucent background, blur, hairline border and soft shadow (`data-scrolled`). The change is
 * a short colour/shadow transition (no movement), removed entirely under reduced motion by the
 * global rule. Content width matches the landing sections (`--container-wide`).
 * Inline navigation from `xl` (eight items); below that it lives in the drawer. Sign in / Register are
 * placeholders until accounts exist (AccountActions, D-13).
 */
export function SiteHeader() {
  const pathname = usePathname();
  const items = useSiteNav();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return (
    <header
      data-scrolled={scrolled}
      className="sticky top-0 z-[var(--z-index-header)] border-b border-transparent bg-background/50 transition-[background-color,border-color,box-shadow] duration-[var(--duration-base)] ease-out supports-[backdrop-filter]:backdrop-blur-sm data-[scrolled=true]:border-border/80 data-[scrolled=true]:bg-background/95 data-[scrolled=true]:shadow-elevation-2 data-[scrolled=true]:supports-[backdrop-filter]:bg-background/75 data-[scrolled=true]:supports-[backdrop-filter]:backdrop-blur-xl"
    >
      <div className="mx-auto grid h-16 max-w-[var(--container-wide)] grid-cols-[1fr_auto] items-center gap-4 px-4 sm:px-6 lg:px-8 xl:grid-cols-[auto_1fr_auto]">
        <div className="flex min-w-0 items-center">
          <Brand mark />
        </div>

        <nav aria-label="Main" className="hidden justify-self-center xl:block">
          <ul className="flex items-center gap-0.5 rounded-xl border border-border/80 bg-background/70 p-1 shadow-elevation-1">
            {items.map((item) => {
              const active = isActivePath(pathname, item.href, "/");
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.soon ? soonLabel(item.label) : undefined}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors duration-[var(--duration-fast)] outline-none hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground"
                  >
                    {item.label}
                    {item.soon && <SoonBadge />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex items-center justify-end gap-1.5">
          <ThemeToggle />
          <span aria-hidden="true" className="mx-1.5 hidden h-5 w-px bg-border sm:block" />
          <div className="hidden sm:flex">
            <AccountActions />
          </div>
          <SiteMobileNav />
        </div>
      </div>
    </header>
  );
}
