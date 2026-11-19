/**
 * Navigation structure for the application shells. Routes listed here exist as placeholder
 * pages until their roadmap phase delivers them (`phase`). No access control is applied yet:
 * authentication and RBAC are Phase 3b (blocked by D-13).
 */

import {
  BookOpenIcon,
  BotIcon,
  ChartLineIcon,
  ClipboardCheckIcon,
  CpuIcon,
  CreditCardIcon,
  FileCheckIcon,
  HeadphonesIcon,
  LayoutDashboardIcon,
  LibraryIcon,
  MicIcon,
  PenLineIcon,
  ScrollTextIcon,
  SettingsIcon,
  TargetIcon,
  UploadIcon,
  UsersIcon,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Roadmap phase that implements this area (docs/DEVELOPMENT_ROADMAP.md). */
  phase: string;
  description: string;
};

export const studentNav: readonly NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboardIcon,
    phase: "11",
    description: "Your progress, recent activity and recommendations.",
  },
  {
    href: "/library",
    label: "Book library",
    icon: LibraryIcon,
    phase: "6",
    description: "Browse IELTS books, editions and tests.",
  },
  {
    href: "/practice",
    label: "Practice",
    icon: TargetIcon,
    phase: "7",
    description: "Practise by module, section or question type.",
  },
  {
    href: "/listening",
    label: "Listening",
    icon: HeadphonesIcon,
    phase: "7",
    description: "Listening practice and exam-mode tests with instant scoring and review.",
  },
  {
    href: "/reading",
    label: "Reading",
    icon: BookOpenIcon,
    phase: "7",
    description: "Academic Reading passages with every question type, timing and evidence review.",
  },
  {
    href: "/mock-tests",
    label: "Mock tests",
    icon: ClipboardCheckIcon,
    phase: "7",
    description: "Full and module-level timed examinations.",
  },
  {
    href: "/writing",
    label: "Writing",
    icon: PenLineIcon,
    phase: "9",
    description: "Writing tasks with AI-estimated feedback.",
  },
  {
    href: "/speaking",
    label: "Speaking",
    icon: MicIcon,
    phase: "10",
    description: "Practise speaking with the AI examiner.",
  },
  {
    href: "/progress",
    label: "Progress",
    icon: ChartLineIcon,
    phase: "11",
    description: "Band estimates and trends across modules.",
  },
  {
    href: "/coach",
    label: "AI coach",
    icon: BotIcon,
    phase: "11",
    description: "Personalised study plans and guidance.",
  },
];

export const adminNav: readonly NavItem[] = [
  {
    href: "/admin",
    label: "Overview",
    icon: LayoutDashboardIcon,
    phase: "11",
    description: "Platform overview.",
  },
  {
    href: "/admin/users",
    label: "Users",
    icon: UsersIcon,
    phase: "3b",
    description: "User and role management.",
  },
  {
    href: "/admin/content",
    label: "Content",
    icon: BookOpenIcon,
    phase: "6",
    description: "Books, editions, tests and questions.",
  },
  {
    href: "/admin/imports",
    label: "Imports",
    icon: UploadIcon,
    phase: "6",
    description: "Bulk content imports with dry-run validation.",
  },
  {
    href: "/admin/reviews",
    label: "Reviews",
    icon: FileCheckIcon,
    phase: "6",
    description: "Content review and publishing.",
  },
  {
    href: "/admin/billing",
    label: "Billing",
    icon: CreditCardIcon,
    phase: "12",
    description: "Plans, subscriptions and payments.",
  },
  {
    href: "/admin/ai-usage",
    label: "AI usage",
    icon: CpuIcon,
    phase: "8",
    description: "AI requests, cost and provider routing.",
  },
  {
    href: "/admin/audit-log",
    label: "Audit log",
    icon: ScrollTextIcon,
    phase: "3b",
    description: "Inspect privileged actions.",
  },
  {
    href: "/admin/settings",
    label: "Settings",
    icon: SettingsIcon,
    phase: "later",
    description: "System configuration and feature flags.",
  },
];

export type LinkItem = { href: string; label: string };
/** `soon`: the route exists but only shows a "Not available yet" placeholder. */
export type PublicNavItem = LinkItem & { soon?: boolean };

/**
 * Public header navigation. Kept short on purpose. Unfinished areas are marked `soon` and
 * rendered with a visible "Soon" badge (and "(coming soon)" for screen readers), so the header
 * never presents a placeholder as a working feature. Ops pages (System status) live in the footer.
 */
export const publicNav: readonly PublicNavItem[] = [
  { href: "/", label: "Home" },
  // The four modules: sections of the landing page (these anchors work today).
  { href: "/#listening", label: "Listening" },
  { href: "/#reading", label: "Reading" },
  { href: "/#writing", label: "Writing" },
  { href: "/#speaking", label: "Speaking" },
  { href: "/library", label: "Library", soon: true },
  { href: "/practice", label: "Practice", soon: true },
  { href: "/coach", label: "AI coach", soon: true },
];

/**
 * Header navigation once a student is signed in: the app sections, in the same main-website header
 * (no separate app shell). Built areas are plain links; planned ones carry the "Soon" badge and
 * open their honest placeholder page. Home stays one click away through the logo; the library
 * is listed in the footer.
 */
export const memberNav: readonly PublicNavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/listening", label: "Listening" },
  { href: "/reading", label: "Reading" },
  { href: "/writing", label: "Writing" },
  { href: "/speaking", label: "Speaking" },
  { href: "/mock-tests", label: "Mock tests", soon: true },
  { href: "/progress", label: "Progress", soon: true },
  { href: "/coach", label: "AI coach", soon: true },
];

/**
 * A footer entry. With `href` it is a link (`soon`: the route exists but only shows a
 * placeholder). Without `href` the page does not exist yet: it is shown as plain, non-link text
 * with its status, so the footer never presents a missing page as working.
 */
export type FooterItem =
  | (PublicNavItem & { status?: never })
  | { label: string; href?: never; soon?: never; status: "planned" | "pending-approval" };

/** Footer groups: Product (landing-page sections), Resources, Company, Legal. */
export const footerNav: readonly { label: string; items: readonly FooterItem[] }[] = [
  {
    label: "Product",
    // Sections of the landing page: these anchors work today.
    items: [
      { href: "/#listening", label: "Listening" },
      { href: "/#reading", label: "Reading" },
      { href: "/#writing", label: "Writing" },
      { href: "/#speaking", label: "Speaking" },
      { href: "/#coach", label: "AI Coach" },
      { href: "/#mock-exam", label: "Mock Exams" },
      { href: "/#progress", label: "Progress Tracking" },
    ],
  },
  {
    label: "Resources",
    items: [
      { href: "/library", label: "Study Library", soon: true },
      { href: "/practice", label: "IELTS Preparation", soon: true },
      { label: "Vocabulary Resources", status: "planned" },
      { label: "Learning Guides", status: "planned" },
      { label: "FAQs", status: "planned" },
    ],
  },
  {
    label: "Company",
    items: [
      { label: "About Us", status: "planned" },
      { label: "Contact", status: "planned" },
      { label: "Help Center", status: "planned" },
      { label: "Feedback", status: "planned" },
      { href: "/status", label: "System status" },
    ],
  },
  {
    label: "Legal",
    // Drafts published for review (D-17); cookie use is covered in the Privacy Policy.
    items: [
      { href: "/privacy", label: "Privacy Policy" },
      { href: "/terms", label: "Terms of Service" },
    ],
  },
];

/**
 * Shell sections. Server Components pass only the section key to client navigation components,
 * because nav items contain icon components (functions), which cannot cross the server→client
 * boundary as props.
 */
export type NavSectionKey = "student" | "admin";

export const navSections: Record<
  NavSectionKey,
  { items: readonly NavItem[]; label: string; title: string; rootHref: string; badge?: string }
> = {
  student: {
    items: studentNav,
    label: "Student navigation",
    title: "IELTS MASTER",
    rootHref: "/dashboard",
  },
  admin: {
    items: adminNav,
    label: "Admin navigation",
    title: "IELTS MASTER Admin",
    rootHref: "/admin",
    badge: "Admin",
  },
};

/** Look up a nav item by href (used by placeholder pages so titles stay in one place). */
export function navItem(items: readonly NavItem[], href: string): NavItem {
  const item = items.find((candidate) => candidate.href === href);
  if (!item) throw new Error(`No nav item for ${href}`);
  return item;
}

/** A nav item is active on its own path and on nested paths (except the section root). */
export function isActivePath(pathname: string, href: string, rootHref?: string): boolean {
  if (href === rootHref) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}
