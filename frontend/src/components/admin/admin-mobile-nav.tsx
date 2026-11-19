"use client";

import { MenuIcon } from "lucide-react";
import { useState } from "react";

import { AdminSidebarNav } from "@/components/admin/admin-sidebar-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

/** Below `lg`, the console sidebar moves into a modal drawer (focus-trapped, Esc closes). */
export function AdminMobileNav() {
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          aria-label="Open admin navigation"
        >
          <MenuIcon aria-hidden="true" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 overflow-y-auto bg-sidebar p-4">
        <SheetHeader className="p-0 pb-4">
          <SheetTitle>IELTS MASTER Admin</SheetTitle>
          <SheetDescription className="sr-only">Admin console navigation</SheetDescription>
        </SheetHeader>
        <AdminSidebarNav onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  );
}
