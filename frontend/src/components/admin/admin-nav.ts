/**
 * Super Admin console navigation (sidebar, drawer and breadcrumbs share this one source).
 *
 * `status: "available"` items are working pages. `status: "soon"` items are planned modules:
 * they are rendered as non-interactive entries with a visible "Soon" badge, never as links, so
 * the console never presents an unbuilt feature as working. To ship a module, add its route
 * under `src/app/(admin)/admin/`, set `href`, and flip its status to "available".
 *
 * `permission` names the backend permission the module will require. It only decides what is
 * shown; the backend authorises every request independently.
 */

import {
  BookOpenCheckIcon,
  ChartColumnIcon,
  CreditCardIcon,
  HeadphonesIcon,
  ImageIcon,
  LayoutDashboardIcon,
  type LucideIcon,
  BotIcon,
  MicIcon,
  ScaleIcon,
  PenLineIcon,
  ReceiptIcon,
  ScrollTextIcon,
  SettingsIcon,
  ShieldCheckIcon,
  UsersIcon,
  LibraryBigIcon,
} from "lucide-react";

export type AdminNavItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  description: string;
  permission?: string;
} & ({ status: "available"; href: string } | { status: "soon"; href?: never });

export type AdminNavGroup = { label: string; items: readonly AdminNavItem[] };

export const ADMIN_ROOT = "/admin";

export const adminNavGroups: readonly AdminNavGroup[] = [
  {
    label: "Overview",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        icon: LayoutDashboardIcon,
        status: "available",
        href: ADMIN_ROOT,
        description: "Platform overview and recent administrative activity.",
      },
    ],
  },
  {
    label: "IELTS Content",
    items: [
      {
        id: "listening",
        label: "Listening Management",
        icon: HeadphonesIcon,
        status: "available",
        href: "/admin/listening",
        permission: "content.edit",
        description: "Listening tests, sections, audio and questions.",
      },
      {
        id: "reading",
        label: "Reading Management",
        icon: BookOpenCheckIcon,
        status: "available",
        href: "/admin/reading",
        permission: "content.edit",
        description: "Reading passages, paragraphs and question groups.",
      },
      {
        id: "writing",
        label: "Writing Management",
        icon: PenLineIcon,
        status: "available",
        href: "/admin/writing",
        permission: "content.edit",
        description: "Writing Task 1 and Task 2 prompts and sample answers.",
      },
      {
        id: "speaking",
        label: "Speaking Management",
        icon: MicIcon,
        status: "available",
        href: "/admin/speaking",
        permission: "content.edit",
        description: "Speaking parts, cue cards and examiner questions.",
      },
      {
        id: "examiner",
        label: "AI Examiner",
        icon: BotIcon,
        status: "available",
        href: "/admin/speaking/examiner",
        permission: "content.edit",
        description: "How the AI examiner conducts Speaking tests, and the examiner personas.",
      },
      {
        id: "rubrics",
        label: "Assessment Rubrics",
        icon: ScaleIcon,
        status: "available",
        href: "/admin/rubrics",
        permission: "content.edit",
        description: "Versioned Writing and Speaking criteria used by AI evaluation.",
      },
      {
        id: "question-bank",
        label: "Question Bank",
        icon: LibraryBigIcon,
        status: "soon",
        permission: "content.edit",
        description: "All question types, validation and review status.",
      },
    ],
  },
  {
    label: "Users",
    items: [
      {
        id: "students",
        label: "Student Management",
        icon: UsersIcon,
        status: "soon",
        permission: "users.read",
        description: "Student accounts, status and support actions.",
      },
      {
        id: "admins",
        label: "Admin Management",
        icon: ShieldCheckIcon,
        status: "soon",
        permission: "roles.assign",
        description: "Staff accounts and role assignments.",
      },
    ],
  },
  {
    label: "Business",
    items: [
      {
        id: "subscriptions",
        label: "Subscriptions",
        icon: CreditCardIcon,
        status: "soon",
        permission: "billing.read",
        description: "Plans and student subscriptions.",
      },
      {
        id: "payments",
        label: "Payments",
        icon: ReceiptIcon,
        status: "soon",
        permission: "billing.read",
        description: "Payment records and reconciliation.",
      },
    ],
  },
  {
    label: "Insights",
    items: [
      {
        id: "analytics",
        label: "Analytics & Reports",
        icon: ChartColumnIcon,
        status: "soon",
        permission: "analytics.read",
        description: "Platform-wide learning and usage analytics.",
      },
    ],
  },
  {
    label: "System",
    items: [
      {
        id: "media",
        label: "Media Library",
        icon: ImageIcon,
        status: "soon",
        permission: "media.upload",
        description: "Audio, images and other content assets.",
      },
      {
        id: "audit-logs",
        label: "Audit Logs",
        icon: ScrollTextIcon,
        status: "soon",
        permission: "audit.read",
        description: "Searchable history of privileged actions.",
      },
      {
        id: "settings",
        label: "Settings",
        icon: SettingsIcon,
        status: "soon",
        permission: "system.configure",
        description: "System configuration and feature flags.",
      },
    ],
  },
];

export function adminNavItem(id: string): AdminNavItem {
  for (const group of adminNavGroups) {
    const found = group.items.find((item) => item.id === id);
    if (found) return found;
  }
  throw new Error(`No admin nav item ${id}`);
}

/** Breadcrumb trail for an admin path: "Admin" then the matching available item, if any. */
export function adminBreadcrumbs(pathname: string): { label: string; href?: string }[] {
  const trail: { label: string; href?: string }[] = [{ label: "Admin", href: ADMIN_ROOT }];
  let best: AdminNavItem | undefined;
  for (const group of adminNavGroups) {
    for (const item of group.items) {
      if (item.status !== "available") continue;
      const matches =
        item.href === ADMIN_ROOT
          ? pathname === ADMIN_ROOT
          : pathname === item.href || pathname.startsWith(`${item.href}/`);
      if (matches && (!best || (best.href?.length ?? 0) < item.href.length)) best = item;
    }
  }
  if (best) trail.push({ label: best.label });
  return trail;
}

export function isActiveAdminPath(pathname: string, href: string): boolean {
  if (href === ADMIN_ROOT) return pathname === ADMIN_ROOT;
  return pathname === href || pathname.startsWith(`${href}/`);
}
