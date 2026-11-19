"use client";

import { KeyRoundIcon, LayoutDashboardIcon, LogOutIcon, ShieldIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { Me } from "@/lib/auth/api";
import { useCurrentUser, useSignOut } from "@/lib/auth/hooks";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() ||
    "?"
  );
}

function Avatar({ user, className }: { user: Me; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground",
        className,
      )}
    >
      {initials(user.full_name)}
    </span>
  );
}

/**
 * Account entry points. Signed out: Sign in / Register links. Signed in: an account menu.
 * The user shown here is for display only; the backend authorises every request.
 */
export function AccountActions({
  variant = "header",
  onAction,
}: {
  variant?: "header" | "drawer";
  onAction?: () => void;
}) {
  const { data: user, isPending } = useCurrentUser();
  const signOut = useSignOut();
  const drawer = variant === "drawer";

  if (isPending) {
    return <div aria-hidden="true" className={drawer ? "h-[6.25rem]" : "h-9 w-[10.5rem]"} />;
  }

  if (!user) {
    return drawer ? (
      <div className="flex flex-col gap-2">
        <Button asChild className="h-11 w-full text-[0.9375rem]">
          <Link href="/register" onClick={onAction}>
            Register
          </Link>
        </Button>
        <Button asChild variant="outline" className="h-11 w-full text-[0.9375rem]">
          <Link href="/sign-in" onClick={onAction}>
            Sign in
          </Link>
        </Button>
      </div>
    ) : (
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost" className="h-9 px-3.5">
          <Link href="/sign-in">Sign in</Link>
        </Button>
        <Button asChild className="h-9 px-4 shadow-elevation-1">
          <Link href="/register">Register</Link>
        </Button>
      </div>
    );
  }

  const isStaff = user.permissions.includes("admin.access");
  if (drawer) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-3 rounded-lg bg-muted/60 px-3 py-2.5">
          <Avatar user={user} />
          <div className="min-w-0 text-sm">
            <p className="truncate font-medium">{user.full_name}</p>
            <p className="truncate text-muted-foreground">{user.email}</p>
          </div>
        </div>
        <Button asChild className="h-11 w-full">
          <Link href="/dashboard" onClick={onAction}>
            Go to dashboard
          </Link>
        </Button>
        <Button
          variant="outline"
          className="h-11 w-full"
          onClick={() => {
            onAction?.();
            void signOut();
          }}
        >
          Sign out
        </Button>
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 gap-2 rounded-full pr-3 pl-1"
          aria-label={`Account menu for ${user.full_name}`}
        >
          <Avatar user={user} className="size-7" />
          <span className="hidden max-w-[8rem] truncate text-sm font-medium sm:inline">
            {user.full_name.split(" ")[0]}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium text-foreground">{user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/dashboard">
            <LayoutDashboardIcon aria-hidden="true" />
            Dashboard
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/account/password">
            <KeyRoundIcon aria-hidden="true" />
            Change password
          </Link>
        </DropdownMenuItem>
        {isStaff && (
          <DropdownMenuItem asChild>
            <Link href="/admin">
              <ShieldIcon aria-hidden="true" />
              Admin area
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOutIcon aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
