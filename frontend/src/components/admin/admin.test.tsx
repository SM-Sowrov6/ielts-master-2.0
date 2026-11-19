import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { adminBreadcrumbs, adminNavGroups } from "@/components/admin/admin-nav";
import { AdminShell } from "@/components/admin/admin-shell";
import {
  ContentOverviewWidget,
  ContentQuickAccess,
  describeAction,
  RecentActivityWidget,
  SystemOverviewWidget,
  UsersOverviewWidget,
  WelcomePanel,
} from "@/components/admin/dashboard/widgets";
import { SignInForm } from "@/components/auth/sign-in-form";
import type { Me } from "@/lib/auth/api";
import { destinationAfterSignIn } from "@/lib/auth/redirect";
import { axeViolations } from "@/test/axe";
import { SAMPLE_USER, renderWithProviders } from "@/test/render";

const pathname = vi.hoisted(() => ({ current: "/admin" }));
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  useRouter: () => router,
}));

const SUPER_ADMIN: Me = {
  id: "0190f0c2-7d1c-7a00-8000-0000000000aa",
  email: "owner@example.test",
  full_name: "Platform Owner",
  email_verified: true,
  roles: ["super_admin"],
  permissions: ["admin.access", "audit.read", "content.edit", "system.configure", "users.read"],
};

const ok = (body: unknown = {}, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => {
  vi.clearAllMocks();
  pathname.current = "/admin";
  document.documentElement.lang = "en";
  document.title = "Admin dashboard · IELTS MASTER 2.0";
});

describe("destinationAfterSignIn (role-aware redirect)", () => {
  const staff = { permissions: ["admin.access"] };
  const student = { permissions: [] as string[] };
  it.each([
    [staff, undefined, "/admin"],
    [student, undefined, "/"], // students stay on the main website
    [staff, "/admin/settings", "/admin/settings"],
    [student, "/admin", "/"], // students are never sent into the console
    [student, "/admin/users?x=1", "/"],
    [student, "/administer-not-admin", "/administer-not-admin"],
    [staff, "/library", "/library"],
    [staff, "/dashboard", "/dashboard"], // an explicit choice is respected
    [staff, "//evil.example", "/admin"], // unsafe input = no preference
    [student, "https://evil.example", "/"],
    [student, "/listening", "/listening"],
  ])("%j next=%s -> %s", (user, next, expected) => {
    expect(destinationAfterSignIn(user, next)).toBe(expected);
  });

  it("signs a staff account in to the admin console", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SignInForm />, {
      routes: { "POST /api/v1/auth/login": () => ok(SUPER_ADMIN) },
    });
    await user.type(screen.getByLabelText("Email address"), SUPER_ADMIN.email);
    await user.type(screen.getByLabelText("Password"), "operator chosen passphrase");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/admin"));
  });

  it("keeps students out of the console even when asked to go there", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SignInForm next="/admin" />, {
      routes: { "POST /api/v1/auth/login": () => ok(SAMPLE_USER) },
    });
    await user.type(screen.getByLabelText("Email address"), SAMPLE_USER.email);
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });
});

describe("admin navigation", () => {
  it("has the planned groups; only the dashboard and the four modules plus rubrics are available", () => {
    expect(adminNavGroups.map((g) => g.label)).toEqual([
      "Overview",
      "IELTS Content",
      "Users",
      "Business",
      "Insights",
      "System",
    ]);
    const available = adminNavGroups
      .flatMap((g) => g.items)
      .filter((i) => i.status === "available");
    expect(available.map((i) => i.id)).toEqual([
      "dashboard",
      "listening",
      "reading",
      "writing",
      "speaking",
      "examiner",
      "rubrics",
    ]);
  });

  it("builds breadcrumbs from available pages only", () => {
    expect(adminBreadcrumbs("/admin")).toEqual([
      { label: "Admin", href: "/admin" },
      { label: "Dashboard" },
    ]);
    expect(adminBreadcrumbs("/admin/users")).toEqual([{ label: "Admin", href: "/admin" }]);
  });
});

describe("AdminShell", () => {
  it("renders the console chrome with honest navigation and no a11y violations", async () => {
    const { container } = renderWithProviders(
      <AdminShell user={SUPER_ADMIN}>
        <h1>Dashboard</h1>
      </AdminShell>,
      { me: SUPER_ADMIN },
    );
    expect(container.querySelector("[data-shell='admin']")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Skip to main content" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");

    const nav = screen.getByRole("navigation", { name: "Admin navigation" });
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // Built modules are links; planned modules are visible but are not links.
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.getAttribute("href")),
    ).toEqual([
      "/admin",
      "/admin/listening",
      "/admin/reading",
      "/admin/writing",
      "/admin/speaking",
      "/admin/speaking/examiner",
      "/admin/rubrics",
    ]);
    for (const label of ["Question Bank", "Admin Management", "Settings"]) {
      const entry = within(nav).getByText(label).closest("[data-status='soon']");
      expect(entry).not.toBeNull();
      expect(entry).toHaveTextContent(`${label} (coming soon)`);
    }
    for (const group of ["IELTS Content", "Users", "Business", "Insights", "System"]) {
      expect(within(nav).getByRole("heading", { name: group })).toBeInTheDocument();
    }

    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByText("Dashboard")).toHaveAttribute("aria-current", "page");
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });

  it("is responsive: persistent sidebar from lg, drawer below it", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <AdminShell user={SUPER_ADMIN}>
        <h1>Dashboard</h1>
      </AdminShell>,
      { me: SUPER_ADMIN },
    );
    const aside = container.querySelector("aside");
    expect(aside).toHaveClass("hidden", "lg:flex");
    const trigger = screen.getByRole("button", { name: "Open admin navigation" });
    expect(trigger).toHaveClass("lg:hidden");
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "IELTS MASTER Admin" });
    const drawerNav = within(dialog).getByRole("navigation", { name: "Admin navigation" });
    await user.click(within(drawerNav).getByRole("link", { name: "Dashboard" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the administrator and signs out through the server", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(
      <AdminShell user={SUPER_ADMIN}>
        <h1>Dashboard</h1>
      </AdminShell>,
      {
        me: SUPER_ADMIN,
        routes: { "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }) },
      },
    );
    await user.click(screen.getByRole("button", { name: "Account menu for Platform Owner" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText(SUPER_ADMIN.email)).toBeInTheDocument();
    expect(within(menu).getByText("Super admin")).toBeInTheDocument();
    await user.click(within(menu).getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
    const logout = fetchMock.mock.calls
      .map(([request]) => request)
      .find((r) => r instanceof Request && r.url.endsWith("/api/v1/auth/logout")) as Request;
    expect(logout.method).toBe("POST");
    expect(logout.headers.get("x-csrf-token")).toBe("test-csrf-token");
  });
});

describe("dashboard widgets", () => {
  it("welcomes the administrator with their real account details", () => {
    renderWithProviders(<WelcomePanel user={SUPER_ADMIN} />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Welcome back, Platform" }),
    ).toBeInTheDocument();
    expect(screen.getByText(SUPER_ADMIN.email)).toBeInTheDocument();
    expect(screen.getByText("Super admin")).toBeInTheDocument();
    expect(screen.getByText(String(SUPER_ADMIN.permissions.length))).toBeInTheDocument();
  });

  it("links built content modules and lists the rest as coming soon, without links", () => {
    const { container } = renderWithProviders(<ContentQuickAccess />);
    expect(screen.getByRole("link", { name: "Listening Management" })).toHaveAttribute(
      "href",
      "/admin/listening",
    );
    expect(container.querySelectorAll("a")).toHaveLength(6);
    expect(container.querySelectorAll("[data-status='soon']")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Reading Management" })).toHaveAttribute(
      "href",
      "/admin/reading",
    );
  });

  it("shows real counts, empty states and permission refusals", () => {
    const { rerender } = renderWithProviders(
      <ContentOverviewWidget
        read={{
          status: "ok",
          data: {
            books: 2,
            tests: 7,
            versions_by_status: { draft: 1, in_review: 3, published: 5, archived: 0 },
            published_modules: { listening: 4, reading: 4, writing: 0, speaking: 0 },
          },
        }}
      />,
    );
    expect(screen.getByText("Tests").nextSibling).toHaveTextContent("7");
    expect(screen.getByText("Awaiting review").nextSibling).toHaveTextContent("3");
    expect(screen.getByText("Listening: 4")).toBeInTheDocument();

    rerender(
      <ContentOverviewWidget
        read={{
          status: "ok",
          data: {
            books: 0,
            tests: 0,
            versions_by_status: { draft: 0, in_review: 0, published: 0, archived: 0 },
            published_modules: { listening: 0, reading: 0, writing: 0, speaking: 0 },
          },
        }}
      />,
    );
    expect(screen.getByText("No books or tests have been imported yet.")).toBeInTheDocument();

    rerender(<UsersOverviewWidget read={{ status: "forbidden" }} />);
    expect(
      screen.getByText("Your role does not include access to this information."),
    ).toBeInTheDocument();

    rerender(<RecentActivityWidget read={{ status: "unavailable" }} />);
    expect(screen.getByText(/could not be loaded/)).toBeInTheDocument();
  });

  it("renders users and audit activity from backend data", () => {
    const { rerender } = renderWithProviders(
      <UsersOverviewWidget
        read={{
          status: "ok",
          data: {
            total: 12,
            by_status: { pending: 2, active: 10, suspended: 0, deleted: 0 },
            students: 11,
            staff_by_role: { super_admin: 1, admin: 0, content_manager: 0, reviewer: 0 },
          },
        }}
      />,
    );
    expect(screen.getByText("Students").nextSibling).toHaveTextContent("11");
    expect(screen.getByText("10 active · 2 unverified")).toBeInTheDocument();
    expect(screen.getByText("Super admin: 1")).toBeInTheDocument();

    rerender(
      <RecentActivityWidget
        read={{
          status: "ok",
          data: {
            items: [
              {
                id: "0190f0c2-7d1c-7a00-8000-0000000000b1",
                created_at: "2026-11-19T08:30:00Z",
                action: "identity.login.succeeded",
                entity_type: "user",
                entity_id: SUPER_ADMIN.id,
                actor: { id: SUPER_ADMIN.id, name: "Platform Owner" },
              },
              {
                id: "0190f0c2-7d1c-7a00-8000-0000000000b2",
                created_at: "2026-11-19T08:00:00Z",
                action: "identity.role.granted",
                entity_type: "user",
                entity_id: SUPER_ADMIN.id,
                actor: null,
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("Login succeeded")).toBeInTheDocument();
    expect(screen.getByText(/System or operator \(CLI\)/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    rerender(<RecentActivityWidget read={{ status: "ok", data: { items: [] } }} />);
    expect(screen.getByText("No audited activity yet.")).toBeInTheDocument();
  });

  it("reports service readiness without inventing status", () => {
    const { rerender } = renderWithProviders(
      <SystemOverviewWidget
        system={{ status: "ok", overall: "ok", checks: { database: "ok", redis: "unavailable" } }}
      />,
    );
    expect(screen.getByText("Database").nextSibling).toHaveTextContent("Operational");
    expect(screen.getByText("Cache & rate limits").nextSibling).toHaveTextContent("Unavailable");
    rerender(<SystemOverviewWidget system={{ status: "unavailable" }} />);
    expect(screen.getByText("Backend API").nextSibling).toHaveTextContent("Unavailable");
  });

  it("derives readable action labels from stable codes", () => {
    expect(describeAction("identity.role.granted")).toBe("Role granted");
    expect(describeAction("content.version.published")).toBe("Version published");
    expect(describeAction("plain")).toBe("Plain");
  });
});
