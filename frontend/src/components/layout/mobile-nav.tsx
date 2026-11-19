"use client";

import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { navSections, type NavSectionKey } from "@/components/layout/nav-config";
import { NavList } from "@/components/layout/nav-list";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/** Below `lg`, the sidebar navigation moves into a modal drawer (focus-trapped, Esc closes). */
export function MobileNav({ section }: { section: NavSectionKey }) {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation menu">
          <MenuIcon aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 bg-sidebar p-4">
        <SheetHeader className="p-0 pb-4">
          <SheetTitle>{navSections[section].title}</SheetTitle>
          <SheetDescription className="sr-only">Site navigation</SheetDescription>
        </SheetHeader>
        <NavList section={section} onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}
