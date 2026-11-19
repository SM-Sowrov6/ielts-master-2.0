"use client";

import { KeyRoundIcon, LayoutDashboardIcon, LogOutIcon } from "lucide-react";
import Link from "next/link";

import { roleLabel, sortRoles } from "@/components/admin/role-label";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Me } from "@/lib/auth/api";
import { useSignOut } from "@/lib/auth/hooks";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    ((parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")).toUpperCase() ||
    "?"
  );
}

/**
 * Administrator profile menu. `user` comes from the server-verified staff session (display only).
 * Sign out revokes the session on the server (POST /auth/logout, CSRF-protected).
 */
export function AdminAccountMenu({ user }: { user: Me }) {
  const signOut = useSignOut();
  const primaryRole = sortRoles(user.roles)[0];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 gap-2 rounded-full pr-3 pl-1"
          aria-label={`Account menu for ${user.full_name}`}
        >
          <span
            aria-hidden="true"
            className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground"
          >
            {initials(user.full_name)}
          </span>
          <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:inline">
            {user.full_name.split(" ")[0]}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium text-foreground">{user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
          {primaryRole && (
            <p className="mt-1 text-xs font-medium text-primary">{roleLabel(primaryRole)}</p>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/account/password">
            <KeyRoundIcon aria-hidden="true" />
            Change password
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/dashboard">
            <LayoutDashboardIcon aria-hidden="true" />
            Student area
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOutIcon aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
