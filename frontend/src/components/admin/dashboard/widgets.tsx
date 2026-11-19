/**
 * Super Admin dashboard widgets. Each widget renders one backend read (`AdminRead`) and handles
 * its own states: real data, "no data yet" (empty), "not permitted" (the backend refused), or
 * "unavailable". Nothing here invents numbers. Future modules add a widget in this folder and
 * place it in the dashboard grid (app/(admin)/admin/page.tsx).
 */

import {
  ActivityIcon,
  BookOpenIcon,
  CircleCheckIcon,
  CircleXIcon,
  type LucideIcon,
  LockIcon,
  ServerIcon,
  ShieldCheckIcon,
  UsersIcon,
} from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { adminNavGroups } from "@/components/admin/admin-nav";
import { roleLabel, sortRoles } from "@/components/admin/role-label";
import { SoonBadge } from "@/components/layout/soon-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { AdminRead, AuditLogPage, ContentOverview, UsersOverview } from "@/lib/admin/server";
import type { Me } from "@/lib/auth/api";
import { cn } from "@/lib/utils";

export type SystemStatus =
  { status: "ok"; overall: string; checks: Record<string, string> } | { status: "unavailable" };

const number = new Intl.NumberFormat("en");

// --------------------------------------------------------------------------- building blocks
function Widget({
  title,
  description,
  icon: Icon,
  children,
  className,
}: {
  title: string;
  description?: string;
  icon: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("gap-5", className)}>
      <CardHeader>
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary"
          >
            <Icon className="size-4" />
          </span>
          <CardTitle>
            <h2 className="font-heading text-base font-semibold">{title}</h2>
          </CardTitle>
        </div>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Notice({ tone = "muted", children }: { tone?: "muted" | "warning"; children: ReactNode }) {
  return (
    <p
      className={cn(
        "rounded-lg border border-dashed px-4 py-5 text-center text-sm",
        tone === "warning" ? "border-warning/40 text-foreground" : "text-muted-foreground",
      )}
    >
      {children}
    </p>
  );
}

function ReadState({ read }: { read: { status: "forbidden" | "unavailable" } }) {
  if (read.status === "forbidden") {
    return (
      <Notice>
        <LockIcon className="mr-1.5 inline size-3.5 align-[-2px]" aria-hidden="true" />
        Your role does not include access to this information.
      </Notice>
    );
  }
  return <Notice tone="warning">This information could not be loaded. Try again shortly.</Notice>;
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-lg bg-muted/50 px-4 py-3">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-heading text-2xl font-semibold tabular-nums">
        {number.format(value)}
      </dd>
      {hint && <dd className="text-xs text-muted-foreground">{hint}</dd>}
    </div>
  );
}

// --------------------------------------------------------------------------- welcome
export function WelcomePanel({ user }: { user: Me }) {
  const roles = sortRoles(user.roles);
  const firstName = user.full_name.split(" ")[0] ?? user.full_name;
  return (
    <section
      aria-labelledby="admin-welcome"
      className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-elevation-1 sm:p-8"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-primary/10 blur-3xl"
      />
      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <p className="text-sm font-medium text-primary">Super Admin console</p>
          <h1
            id="admin-welcome"
            className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl"
          >
            Welcome back, {firstName}
          </h1>
          <p className="max-w-[var(--container-prose)] text-muted-foreground">
            Manage IELTS MASTER from one place. Modules marked &ldquo;Soon&rdquo; are planned and
            not yet available.
          </p>
        </div>
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3 lg:min-w-[26rem]">
          <div className="min-w-0">
            <dt className="text-muted-foreground">Signed in as</dt>
            <dd className="truncate font-medium">{user.email}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="mt-0.5 flex flex-wrap gap-1">
              {roles.map((role) => (
                <Badge key={role} variant={role === "super_admin" ? "default" : "secondary"}>
                  {roleLabel(role)}
                </Badge>
              ))}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Permissions</dt>
            <dd className="font-medium tabular-nums">{user.permissions.length}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- content
export function ContentQuickAccess() {
  const content = adminNavGroups.find((group) => group.label === "IELTS Content")?.items ?? [];
  return (
    <Widget
      title="IELTS content management"
      description="Listening, Reading, Writing and Speaking management and the assessment rubrics are available. The question bank is planned."
      icon={BookOpenIcon}
    >
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {content.map((item) => {
          const Icon = item.icon;
          return (
            <li
              key={item.id}
              className="relative flex flex-col gap-2 rounded-lg border bg-background/60 p-4 focus-within:ring-2 focus-within:ring-ring"
              data-status={item.status}
            >
              <div className="flex items-center justify-between gap-2">
                <Icon className="size-5 text-muted-foreground" aria-hidden="true" />
                {item.status === "soon" && <SoonBadge />}
              </div>
              {item.status === "available" ? (
                <Link
                  href={item.href}
                  className="text-sm font-medium text-primary underline-offset-4 after:absolute after:inset-0 hover:underline"
                >
                  {item.label}
                </Link>
              ) : (
                <p className="text-sm font-medium">
                  {item.label}
                  <span className="sr-only"> (coming soon)</span>
                </p>
              )}
              <p className="text-xs text-muted-foreground">{item.description}</p>
            </li>
          );
        })}
      </ul>
    </Widget>
  );
}

const MODULE_LABELS: Record<string, string> = {
  listening: "Listening",
  reading: "Reading",
  writing: "Writing",
  speaking: "Speaking",
};

export function ContentOverviewWidget({ read }: { read: AdminRead<ContentOverview> }) {
  return (
    <Widget
      title="Content overview"
      description="Live counts from the content catalogue."
      icon={BookOpenIcon}
    >
      {read.status !== "ok" ? (
        <ReadState read={read} />
      ) : read.data.books === 0 && read.data.tests === 0 ? (
        <Notice>No books or tests have been imported yet.</Notice>
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Books" value={read.data.books} />
            <Stat label="Tests" value={read.data.tests} />
            <Stat label="Published versions" value={read.data.versions_by_status.published ?? 0} />
            <Stat
              label="Awaiting review"
              value={read.data.versions_by_status.in_review ?? 0}
              hint={`${number.format(read.data.versions_by_status.draft ?? 0)} draft`}
            />
          </dl>
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted-foreground">
              Published modules by skill
            </h3>
            <ul className="flex flex-wrap gap-2">
              {Object.entries(MODULE_LABELS).map(([key, label]) => (
                <li key={key}>
                  <Badge variant="outline" className="tabular-nums">
                    {label}: {number.format(read.data.published_modules[key] ?? 0)}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Widget>
  );
}

// --------------------------------------------------------------------------- users
export function UsersOverviewWidget({ read }: { read: AdminRead<UsersOverview> }) {
  return (
    <Widget title="Accounts" description="Live counts of registered accounts." icon={UsersIcon}>
      {read.status !== "ok" ? (
        <ReadState read={read} />
      ) : read.data.total === 0 ? (
        <Notice>No accounts exist yet.</Notice>
      ) : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3">
            <Stat label="Students" value={read.data.students} />
            <Stat
              label="All accounts"
              value={read.data.total}
              hint={`${number.format(read.data.by_status.active ?? 0)} active · ${number.format(read.data.by_status.pending ?? 0)} unverified`}
            />
          </dl>
          <div>
            <h3 className="mb-2 text-xs font-medium text-muted-foreground">Staff by role</h3>
            <ul className="flex flex-wrap gap-2">
              {sortRoles(Object.keys(read.data.staff_by_role)).map((role) => (
                <li key={role}>
                  <Badge variant="outline" className="tabular-nums">
                    {roleLabel(role)}: {number.format(read.data.staff_by_role[role] ?? 0)}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Widget>
  );
}

// --------------------------------------------------------------------------- activity
const time = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

/** "identity.login.succeeded" -> "Login succeeded" (labels stay derivable from stable codes). */
export function describeAction(action: string): string {
  const parts = action.split(".");
  const words = parts.slice(1).join(" ").replaceAll("_", " ");
  const text = words || action;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function RecentActivityWidget({ read }: { read: AdminRead<AuditLogPage> }) {
  return (
    <Widget
      title="Recent activity"
      description="The latest entries in the audit log (times in UTC)."
      icon={ActivityIcon}
    >
      {read.status !== "ok" ? (
        <ReadState read={read} />
      ) : read.data.items.length === 0 ? (
        <Notice>No audited activity yet.</Notice>
      ) : (
        <ol className="divide-y">
          {read.data.items.map((entry) => (
            <li key={entry.id} className="flex items-start justify-between gap-4 py-2.5 text-sm">
              <div className="min-w-0">
                <p className="font-medium">{describeAction(entry.action)}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {entry.actor
                    ? (entry.actor.name ?? "Deleted account")
                    : "System or operator (CLI)"}{" "}
                  · <span className="font-mono">{entry.action}</span>
                </p>
              </div>
              <time
                dateTime={entry.created_at}
                className="shrink-0 text-xs text-muted-foreground tabular-nums"
              >
                {time.format(new Date(entry.created_at))}
              </time>
            </li>
          ))}
        </ol>
      )}
    </Widget>
  );
}

// --------------------------------------------------------------------------- system
const CHECK_LABELS: Record<string, string> = { database: "Database", redis: "Cache & rate limits" };

export function SystemOverviewWidget({ system }: { system: SystemStatus }) {
  const rows =
    system.status === "ok"
      ? [
          { name: "Backend API", ok: system.overall === "ok" },
          ...Object.entries(system.checks).map(([name, value]) => ({
            name: CHECK_LABELS[name] ?? name,
            ok: value === "ok",
          })),
        ]
      : [{ name: "Backend API", ok: false }];
  return (
    <Widget title="System overview" description="Live service readiness." icon={ServerIcon}>
      <div className="space-y-4">
        <ul className="divide-y rounded-lg border">
          {rows.map((row) => (
            <li key={row.name} className="flex items-center justify-between px-4 py-2.5 text-sm">
              <span>{row.name}</span>
              <span
                className={cn(
                  "flex items-center gap-1.5 font-medium",
                  row.ok ? "text-success" : "text-destructive",
                )}
              >
                {row.ok ? (
                  <CircleCheckIcon className="size-4" aria-hidden="true" />
                ) : (
                  <CircleXIcon className="size-4" aria-hidden="true" />
                )}
                {row.ok ? "Operational" : "Unavailable"}
              </span>
            </li>
          ))}
        </ul>
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <ShieldCheckIcon className="mt-px size-3.5 shrink-0" aria-hidden="true" />
          Access is verified by the server on every request. Your session ends when you sign out,
          after inactivity, or when your role changes.
        </p>
      </div>
    </Widget>
  );
}
