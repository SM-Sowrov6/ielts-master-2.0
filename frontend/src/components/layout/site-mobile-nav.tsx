"use client";

import { MenuIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AccountActions } from "@/components/layout/account-actions";
import { BrandMark } from "@/components/layout/brand";
import { isActivePath } from "@/components/layout/nav-config";
import { SoonBadge, soonLabel } from "@/components/layout/soon-badge";
import { useSiteNav } from "@/components/layout/use-site-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/**
 * Below `lg`, the public navigation moves into a modal drawer (Radix Dialog: focus trapped,
 * Esc and the close button close it, focus returns to the menu button). It also closes after
 * navigation and when the viewport grows past `lg`, where the inline navigation takes over.
 */
export function SiteMobileNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const items = useSiteNav();
  const menuRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 64rem)");
    const close = () => {
      if (desktop.matches) setOpen(false);
    };
    desktop.addEventListener("change", close);
    return () => desktop.removeEventListener("change", close);
  }, []);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-9 xl:hidden"
          aria-label="Open site menu"
        >
          <MenuIcon aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-[min(20rem,86vw)] gap-0 p-0"
        onOpenAutoFocus={(event) => {
          // Radix skips links when choosing initial focus (it would land on a placeholder
          // account button); start on the first menu item instead.
          const first = menuRef.current?.querySelector("a");
          if (first) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <SheetHeader className="h-16 justify-center border-b px-5 py-0">
          <SheetTitle className="flex items-center gap-2 font-heading text-base font-semibold tracking-tight">
            <BrandMark />
            IELTS MASTER
          </SheetTitle>
          <SheetDescription className="sr-only">Site navigation</SheetDescription>
        </SheetHeader>
        <nav ref={menuRef} aria-label="Site menu" className="p-3">
          <ul className="space-y-1">
            {items.map((item) => {
              const active = isActivePath(pathname, item.href, "/");
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.soon ? soonLabel(item.label) : undefined}
                    className="flex h-12 items-center justify-between gap-3 rounded-lg px-3 text-base font-medium transition-colors outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring aria-[current=page]:bg-accent aria-[current=page]:text-accent-foreground"
                  >
                    <span>{item.label}</span>
                    {item.soon && <SoonBadge />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-auto border-t p-4">
          <AccountActions variant="drawer" onAction={() => setOpen(false)} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
