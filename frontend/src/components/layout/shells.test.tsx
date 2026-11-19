import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/app-shell";
import { FocusShell } from "@/components/layout/focus-shell";
import { isActivePath, studentNav } from "@/components/layout/nav-config";
import { SiteShell } from "@/components/layout/site-shell";
import { axeViolations } from "@/test/axe";
import { SAMPLE_USER, renderWithProviders } from "@/test/render";

const pathname = vi.hoisted(() => ({ current: "/" }));
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  useRouter: () => router,
}));

beforeEach(() => {
  pathname.current = "/";
  // Provided by the root layout (src/app/layout.tsx: <html lang="en"> + metadata title) in the app.
  document.documentElement.lang = "en";
  document.title = "Test page · IELTS MASTER 2.0";
});

describe("isActivePath", () => {
  it("matches nested paths but keeps the section root exact", () => {
    expect(isActivePath("/admin/users/42", "/admin/users", "/admin")).toBe(true);
    expect(isActivePath("/admin/users", "/admin", "/admin")).toBe(false);
    expect(isActivePath("/admin", "/admin", "/admin")).toBe(true);
    expect(isActivePath("/library-extra", "/library")).toBe(false);
  });
});

describe("AppShell", () => {
  it("has a skip link, landmarks, one main region and marks the current page", async () => {
    pathname.current = "/library";
    const { container } = renderWithProviders(
      <AppShell variant="student">
        <h1>Library</h1>
      </AppShell>,
    );
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("banner")).toBeInTheDocument();

    const nav = screen.getByRole("navigation", { name: "Student navigation" });
    const current = within(nav).getByRole("link", { name: "Book library" });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Dashboard" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });

  it("admin variant uses its own navigation and labels", () => {
    pathname.current = "/admin";
    renderWithProviders(
      <AppShell variant="admin">
        <h1>Overview</h1>
      </AppShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Admin navigation" });
    expect(within(nav).getByRole("link", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Users" })).not.toHaveAttribute("aria-current");
  });

  it("mobile navigation opens as a labelled dialog and closes with Escape", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell variant="student">
        <h1>Dashboard</h1>
      </AppShell>,
    );
    const menuButton = screen.getByRole("button", { name: "Open navigation menu" });
    await user.click(menuButton);
    const drawer = await screen.findByRole("dialog", { name: "IELTS MASTER" });
    expect(within(drawer).getAllByRole("link")).toHaveLength(studentNav.length);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(menuButton).toHaveFocus();
  });
});

describe("SiteShell and FocusShell", () => {
  it("public shell exposes header, main, footer and the estimate disclaimer", async () => {
    const { container } = renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
    );
    expect(screen.getByRole("contentinfo")).toHaveTextContent("not official IELTS results");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    for (const name of ["Product", "Resources", "Company", "Legal"]) {
      expect(screen.getByRole("navigation", { name })).toBeInTheDocument();
    }
    // Product links go to the landing-page sections.
    expect(
      within(screen.getByRole("navigation", { name: "Product" })).getByRole("link", {
        name: "Mock Exams",
      }),
    ).toHaveAttribute("href", "/#mock-exam");
    // Unfinished areas are marked in the footer too.
    expect(
      within(screen.getByRole("navigation", { name: "Resources" })).getByRole("link", {
        name: "Study Library (coming soon)",
      }),
    ).toHaveAttribute("href", "/library");
    // Pages that do not exist are never links; the published legal documents are.
    const legal = screen.getByRole("navigation", { name: "Legal" });
    expect(within(legal).getByRole("link", { name: "Privacy Policy" })).toHaveAttribute(
      "href",
      "/privacy",
    );
    expect(within(legal).getByRole("link", { name: "Terms of Service" })).toHaveAttribute(
      "href",
      "/terms",
    );
    expect(
      within(screen.getByRole("navigation", { name: "Company" })).getAllByRole("link"),
    ).toHaveLength(1);
    // No social links until official accounts exist.
    expect(screen.getByRole("contentinfo").querySelector('a[href^="http"]')).toBeNull();
    expect(screen.getByRole("contentinfo")).toHaveTextContent(
      `© ${new Date().getFullYear()} IELTS MASTER`,
    );
    // Signed out: real links to the account pages.
    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/sign-in",
    );
    expect(screen.getByRole("link", { name: "Register" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("main").className).toContain("max-w-");
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });

  it("public shell full layout leaves width to the page", () => {
    renderWithProviders(
      <SiteShell layout="full">
        <h1>Landing</h1>
      </SiteShell>,
    );
    expect(screen.getByRole("main").className).not.toContain("max-w-");
  });

  it("public mobile menu opens as a labelled dialog and closes with Escape", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
    );
    const menuButton = screen.getByRole("button", { name: "Open site menu" });
    await user.click(menuButton);
    const drawer = await screen.findByRole("dialog", { name: "IELTS MASTER" });
    const menu = within(drawer).getByRole("navigation", { name: "Site menu" });
    expect(within(menu).getByRole("link", { name: "Library (coming soon)" })).toHaveAttribute(
      "href",
      "/library",
    );
    expect(within(menu).getByRole("link", { name: "Home" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(await within(drawer).findByRole("link", { name: "Register" })).toHaveAttribute(
      "href",
      "/register",
    );
    // Initial focus lands on the first menu item, not on a placeholder button.
    expect(within(menu).getByRole("link", { name: "Home" })).toHaveFocus();
    expect(await axeViolations(drawer)).toEqual([]);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(menuButton).toHaveFocus();
  });

  it("public mobile menu closes after choosing a link and from its close button", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
    );
    const menuButton = screen.getByRole("button", { name: "Open site menu" });
    await user.click(menuButton);
    let drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("link", { name: "Practice (coming soon)" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(menuButton);
    drawer = await screen.findByRole("dialog");
    await user.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(menuButton).toHaveFocus();
  });

  it("public header marks the current page and unfinished areas honestly", () => {
    pathname.current = "/library";
    renderWithProviders(
      <SiteShell>
        <h1>Library</h1>
      </SiteShell>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Home",
      "Listening",
      "Reading",
      "Writing",
      "Speaking",
      "LibrarySoon",
      "PracticeSoon",
      "AI coachSoon",
    ]);
    expect(within(nav).getByRole("link", { name: "Library (coming soon)" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Home" })).not.toHaveAttribute("aria-current");
    // The four modules jump to their sections on the landing page.
    expect(within(nav).getByRole("link", { name: "Speaking" })).toHaveAttribute(
      "href",
      "/#speaking",
    );
    // Ops page lives in the footer, not the main navigation.
    expect(within(nav).queryByRole("link", { name: /system status/i })).toBeNull();
    expect(screen.getByRole("link", { name: "System status" })).toBeInTheDocument();
  });

  it("signed-in users get an account menu with their name and sign out", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
      {
        me: { ...SAMPLE_USER, permissions: [] },
        routes: { "POST /api/v1/auth/logout": () => new Response(null, { status: 204 }) },
      },
    );
    const header = screen.getByRole("banner");
    const trigger = await within(header).findByRole("button", {
      name: "Account menu for Amina Rahman",
    });
    expect(within(header).queryByRole("link", { name: "Sign in" })).toBeNull();
    await user.click(trigger);
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByText("amina@example.test")).toBeInTheDocument();
    expect(within(menu).getByRole("menuitem", { name: "Change password" })).toHaveAttribute(
      "href",
      "/account/password",
    );
    expect(within(menu).queryByRole("menuitem", { name: "Admin area" })).toBeNull();
    await user.click(within(menu).getByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
    const logout = fetchMock.mock.calls.find(([input]) =>
      String(input instanceof Request ? input.url : input).includes("/auth/logout"),
    );
    expect(logout).toBeDefined();
    const sent = logout?.[0] instanceof Request ? logout[0] : undefined;
    expect(sent?.headers.get("X-CSRF-Token")).toBe("test-csrf-token");
  });

  it("staff see the admin area link (display only; the server enforces access)", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
      {
        me: {
          ...SAMPLE_USER,
          roles: ["reviewer"],
          permissions: ["admin.access", "content.review"],
        },
      },
    );
    await user.click(await screen.findByRole("button", { name: /Account menu/ }));
    expect(await screen.findByRole("menuitem", { name: "Admin area" })).toHaveAttribute(
      "href",
      "/admin",
    );
  });

  it("public header switches to its elevated style once the page scrolls", () => {
    renderWithProviders(
      <SiteShell>
        <h1>Home</h1>
      </SiteShell>,
    );
    const header = screen.getByRole("banner");
    expect(header).toHaveAttribute("data-scrolled", "false");
    Object.defineProperty(window, "scrollY", { configurable: true, value: 200 });
    act(() => {
      window.dispatchEvent(new Event("scroll"));
    });
    expect(header).toHaveAttribute("data-scrolled", "true");
    Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
    act(() => {
      window.dispatchEvent(new Event("scroll"));
    });
    expect(header).toHaveAttribute("data-scrolled", "false");
  });

  it("focus shell has no site navigation and announces status politely", async () => {
    const { container } = renderWithProviders(
      <FocusShell
        title="Exam room"
        status={<span>59:00</span>}
        footer={<button type="button">Next</button>}
      >
        <h1>Question 1</h1>
      </FocusShell>,
    );
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.getByText("59:00").parentElement).toHaveAttribute("aria-live", "polite");
    expect(await axeViolations(container, { page: true })).toEqual([]);
  });
});
