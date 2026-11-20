import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssistantMarkdown } from "@/components/assistant/assistant-markdown";
import { FloatingAssistant } from "@/components/assistant/floating-assistant";
import { assistantHiddenOn, safeInternalHref } from "@/lib/assistant/routes";
import { loadConversation, saveConversation } from "@/lib/assistant/session";
import { axeViolations } from "@/test/axe";
import { SAMPLE_USER, renderWithProviders } from "@/test/render";
import { render } from "@testing-library/react";

const pathname = { current: "/" };
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

const available = () => json(200, { available: true });

beforeEach(() => {
  pathname.current = "/";
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FloatingAssistant", () => {
  it("shows only a launcher until opened, then a labelled panel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FloatingAssistant />, {
      routes: { "GET /api/v1/assistant/status": available },
    });
    const launcher = await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(launcher).toHaveAttribute("aria-expanded", "false");

    await user.click(launcher);
    const dialog = screen.getByRole("dialog", { name: "IELTS MASTER Assistant" });
    expect(within(dialog).getByText(/I'm your IELTS MASTER assistant/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Message the assistant")).toHaveFocus());
    expect(await axeViolations(dialog)).toEqual([]);
  });

  it("sends the conversation with the current path and renders the reply", async () => {
    pathname.current = "/writing";
    const user = userEvent.setup();
    let sent: unknown;
    renderWithProviders(<FloatingAssistant />, {
      routes: {
        "GET /api/v1/assistant/status": available,
        "POST /api/v1/assistant/chat": async (_init, request) => {
          sent = await request!.json();
          expect(request!.headers.get("X-CSRF-Token")).toBe("test-csrf-token");
          return json(200, {
            role: "assistant",
            content: "Use **PEEL**. See [Writing](/writing).",
          });
        },
      },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    await user.type(screen.getByLabelText("Message the assistant"), "How do I plan?{Enter}");

    expect(await screen.findByText("PEEL")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Writing" })).toHaveAttribute("href", "/writing");
    expect(sent).toEqual({
      messages: [{ role: "user", content: "How do I plan?" }],
      page: { path: "/writing" },
    });
    expect(loadConversation("guest")).toHaveLength(2);
  });

  it("offers a page-aware suggestion", async () => {
    pathname.current = "/reading";
    const user = userEvent.setup();
    renderWithProviders(<FloatingAssistant />, {
      routes: { "GET /api/v1/assistant/status": available },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    expect(
      screen.getByRole("button", { name: "Tips for True / False / Not Given?" }),
    ).toBeInTheDocument();
  });

  it.each([
    ["assistant_rate_limited", 429, /sent a lot of messages/],
    ["assistant_busy", 503, /busy right now/],
  ])("explains %s and lets the user retry", async (code, status, text) => {
    const user = userEvent.setup();
    let calls = 0;
    renderWithProviders(<FloatingAssistant />, {
      routes: {
        "GET /api/v1/assistant/status": available,
        "POST /api/v1/assistant/chat": () => {
          calls += 1;
          return calls === 1
            ? json(status, { code, title: "x", status })
            : json(200, { role: "assistant", content: "Recovered answer" });
        },
      },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    await user.type(screen.getByLabelText("Message the assistant"), "Hello{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Recovered answer")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an offline state when the assistant is not configured", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FloatingAssistant />, {
      routes: { "GET /api/v1/assistant/status": () => json(200, { available: false }) },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    expect(await screen.findByText(/assistant is offline right now/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Message the assistant")).toBeNull();
  });

  it("minimises with Escape and returns focus to the launcher", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FloatingAssistant />, {
      routes: { "GET /api/v1/assistant/status": available },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    await waitFor(() => expect(screen.getByLabelText("Message the assistant")).toHaveFocus());
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Open IELTS MASTER Assistant" })).toHaveFocus();
  });

  it("keeps conversations per user and starts fresh on demand", async () => {
    saveConversation(SAMPLE_USER.id, [
      { role: "user", content: "My earlier question" },
      { role: "assistant", content: "My earlier answer" },
    ]);
    const user = userEvent.setup();
    renderWithProviders(<FloatingAssistant />, {
      me: SAMPLE_USER,
      routes: { "GET /api/v1/assistant/status": available },
    });
    await user.click(await screen.findByRole("button", { name: "Open IELTS MASTER Assistant" }));
    expect(await screen.findByText("My earlier answer")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start a new conversation" }));
    expect(screen.queryByText("My earlier answer")).toBeNull();
    expect(screen.getByText(/Hi Amina!/)).toBeInTheDocument();
    expect(loadConversation(SAMPLE_USER.id)).toEqual([]);
  });

  it.each([
    "/exam/reading/abc",
    "/exam/writing/x",
    "/speaking/sessions/1",
    "/speaking-room/preview",
    "/admin/users",
  ])("is not rendered on %s", async (path) => {
    pathname.current = path;
    const { container } = renderWithProviders(<FloatingAssistant />);
    await act(async () => {});
    expect(container).toBeEmptyDOMElement();
  });
});

describe("assistant helpers", () => {
  it("hides on focused routes only", () => {
    expect(assistantHiddenOn("/exam")).toBe(true);
    expect(assistantHiddenOn("/speaking/rooms/1")).toBe(true);
    expect(assistantHiddenOn("/speaking")).toBe(false);
    expect(assistantHiddenOn("/examples")).toBe(false);
    expect(assistantHiddenOn("/writing")).toBe(false);
  });

  it("only allows same-site links", () => {
    expect(safeInternalHref("/listening/history")).toBe("/listening/history");
    expect(safeInternalHref("https://evil.example")).toBeNull();
    expect(safeInternalHref("//evil.example")).toBeNull();
    expect(safeInternalHref("javascript:alert(1)")).toBeNull();
  });

  it("drops another owner's conversation and tolerates bad storage", () => {
    saveConversation("a", [{ role: "user", content: "secret" }]);
    saveConversation("b", [{ role: "user", content: "mine" }]);
    expect(loadConversation("a")).toEqual([]);
    sessionStorage.setItem("ielts-assistant:c", "{not json");
    expect(loadConversation("c")).toEqual([]);
  });

  it("renders links inside bold text", () => {
    render(<AssistantMarkdown text={"- **[Listening](/listening)**"} />);
    const link = screen.getByRole("link", { name: "Listening" });
    expect(link).toHaveAttribute("href", "/listening");
    expect(link.closest("strong")).not.toBeNull();
  });

  it("renders Markdown safely without external links or HTML", () => {
    render(
      <AssistantMarkdown
        text={
          "**Tip**\n- one\n- two\n\n1. first\n[bad](https://evil.example) <img src=x onerror=alert(1)>"
        }
      />,
    );
    expect(screen.getByText("Tip").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("bad")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
