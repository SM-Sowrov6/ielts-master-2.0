import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RegisterForm } from "@/components/auth/register-form";
import { ResetPasswordForm, VerifyEmail } from "@/components/auth/recovery-forms";
import { SignInForm } from "@/components/auth/sign-in-form";
import { browserApi } from "@/lib/api/client";
import { safeNext } from "@/lib/auth/redirect";
import { isProtectedPath } from "@/proxy";
import { axeViolations } from "@/test/axe";
import { SAMPLE_USER, renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/" }));

const TOKEN = "A".repeat(43);

function problem(status: number, code: string, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ status, code, title, detail }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}
const ok = (body: unknown = {}, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const empty = (status: number) => () => new Response(null, { status });

const OPEN_POLICY = {
  open: true,
  minimum_age: null,
  terms_version: "dev-placeholder",
  privacy_version: "dev-placeholder",
  development_placeholders: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(null, "", "/");
  document.documentElement.lang = "en";
});

describe("safeNext (open-redirect protection)", () => {
  it.each([
    ["/library?x=1", "/library?x=1"],
    [null, "/dashboard"],
    ["https://evil.example", "/dashboard"],
    ["//evil.example", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["javascript:alert(1)", "/dashboard"],
    ["/sign-in", "/dashboard"],
    ["/admin/users", "/admin/users"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });
});

describe("route protection list", () => {
  it("protects private areas but keeps previews and the library public", () => {
    for (const path of ["/dashboard", "/speaking", "/account/password", "/admin", "/admin/users"]) {
      expect(isProtectedPath(path)).toBe(true);
    }
    for (const path of ["/", "/library", "/exam/preview", "/speaking-room/preview", "/sign-in"]) {
      expect(isProtectedPath(path)).toBe(false);
    }
  });
});

describe("SignInForm", () => {
  it("validates, shows generic failures and is accessible", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<SignInForm />, {
      routes: {
        "POST /api/v1/auth/login": () =>
          problem(401, "invalid_credentials", "The email or password is incorrect."),
      },
    });
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email address"), "amina@example.test");
    await user.type(screen.getByLabelText("Password"), "wrong password 1");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("The email or password is incorrect.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveValue(""); // cleared after a failure
    expect(router.replace).not.toHaveBeenCalled();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("toggles password visibility accessibly", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SignInForm />);
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    await user.click(toggle);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("offers a new verification link for unverified accounts", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(<SignInForm />, {
      routes: {
        "POST /api/v1/auth/login": () =>
          problem(403, "email_not_verified", "Verify your email address before signing in."),
        "POST /api/v1/auth/verify-email/resend": () => ok({ status: "accepted", detail: "x" }, 202),
      },
    });
    await user.type(screen.getByLabelText("Email address"), "amina@example.test");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await user.click(await screen.findByRole("button", { name: "Send a new verification link" }));
    expect(await screen.findByText(/a new link is on its way/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([r]) => r instanceof Request && r.url.endsWith("/verify-email/resend"),
      ),
    ).toBe(true);
  });

  it("signs in and goes to a safe next page", async () => {
    const user = userEvent.setup();
    renderWithProviders(<SignInForm next="//evil.example" />, {
      routes: { "POST /api/v1/auth/login": () => ok(SAMPLE_USER) },
    });
    await user.type(screen.getByLabelText("Email address"), "amina@example.test");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });
});

describe("RegisterForm", () => {
  async function fill(user: ReturnType<typeof userEvent.setup>) {
    await user.type(await screen.findByLabelText("Full name"), "Amina Rahman");
    await user.type(screen.getByLabelText("Email address"), "amina@example.test");
    await user.type(screen.getByLabelText("Password"), "correct horse battery");
    await user.click(screen.getByLabelText(/I agree to the Terms of Service/));
    await user.click(screen.getByLabelText(/minimum age requirement/));
  }

  it("shows the closed state when registration is not open", async () => {
    renderWithProviders(<RegisterForm />, {
      routes: {
        "GET /api/v1/auth/registration-policy": () =>
          ok({ ...OPEN_POLICY, open: false, development_placeholders: false }),
      },
    });
    expect(await screen.findByText("Registration isn't open yet")).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("marks development placeholders and requires both confirmations", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(<RegisterForm />, {
      routes: { "GET /api/v1/auth/registration-policy": () => ok(OPEN_POLICY) },
    });
    expect(
      await screen.findByText(/Development build: the age policy and legal documents/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/Accept the Terms of Service/)).toBeInTheDocument();
    expect(screen.getByText("Confirm the age requirement to continue.")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("uses the approved minimum age and narrows the notice to the pending documents", async () => {
    renderWithProviders(<RegisterForm />, {
      routes: {
        "GET /api/v1/auth/registration-policy": () => ok({ ...OPEN_POLICY, minimum_age: 16 }),
      },
    });
    expect(
      await screen.findByLabelText("I confirm I am at least 16 years old."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Terms of Service and Privacy Policy are not published yet/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/age policy/)).toBeNull();
  });

  it("shows the server's password-policy reason on the password field", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />, {
      routes: {
        "GET /api/v1/auth/registration-policy": () => ok(OPEN_POLICY),
        "POST /api/v1/auth/register": () =>
          problem(
            422,
            "password_policy",
            "Choose a stronger password.",
            "This password is too common.",
          ),
      },
    });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("This password is too common.")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows 'check your email' only after the server accepts", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(<RegisterForm />, {
      routes: {
        "GET /api/v1/auth/registration-policy": () => ok(OPEN_POLICY),
        "POST /api/v1/auth/register": () => ok({ status: "accepted", detail: "x" }, 202),
      },
    });
    await fill(user);
    await user.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Check your email" })).toBeInTheDocument();
    expect(screen.getByText("amina@example.test")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(
      ([r]) => r instanceof Request && r.url.endsWith("/auth/register"),
    );
    const request = call?.[0] as Request;
    expect(request.headers.get("X-CSRF-Token")).toBe("test-csrf-token");
    expect(await request.clone().json()).toEqual({
      full_name: "Amina Rahman",
      email: "amina@example.test",
      password: "correct horse battery",
      accept_terms: true,
      age_confirmation: true,
    });
  });
});

describe("token pages", () => {
  it("reset: strips the token from the URL and updates the password", async () => {
    window.history.replaceState(null, "", `/reset-password#token=${TOKEN}`);
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(<ResetPasswordForm />, {
      routes: { "POST /api/v1/auth/password/reset": empty(204) },
    });
    const field = await screen.findByLabelText("New password");
    await waitFor(() => expect(window.location.hash).toBe("")); // removed from the address bar
    await user.type(field, "another long passphrase");
    await user.type(screen.getByLabelText("Repeat new password"), "another long passphrase");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(
      ([r]) => r instanceof Request && r.url.endsWith("/password/reset"),
    );
    expect(await (call?.[0] as Request).clone().json()).toEqual({
      token: TOKEN,
      new_password: "another long passphrase",
    });
  });

  it("reset: missing or rejected tokens show the expired-link state", async () => {
    window.history.replaceState(null, "", "/reset-password");
    renderWithProviders(<ResetPasswordForm />);
    expect(
      await screen.findByRole("heading", { name: "This link is invalid or has expired" }),
    ).toBeInTheDocument();
  });

  it("verify: confirms once and reports success", async () => {
    window.history.replaceState(null, "", `/verify-email#token=${TOKEN}`);
    const { fetchMock } = renderWithProviders(<VerifyEmail />, {
      routes: { "POST /api/v1/auth/verify-email": empty(204) },
    });
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
    const calls = fetchMock.mock.calls.filter(
      ([r]) => r instanceof Request && r.url.endsWith("/verify-email"),
    );
    expect(calls).toHaveLength(1);
  });

  it("verify: an invalid link offers a new one", async () => {
    window.history.replaceState(null, "", `/verify-email#token=${TOKEN}`);
    renderWithProviders(<VerifyEmail />, {
      routes: {
        "POST /api/v1/auth/verify-email": () =>
          problem(400, "token_invalid", "This link is invalid or has expired."),
      },
    });
    expect(
      await screen.findByRole("button", { name: "Send a new verification link" }),
    ).toBeInTheDocument();
  });
});

describe("CSRF middleware", () => {
  it("refreshes the token and retries once when the server rejects it", async () => {
    let attempts = 0;
    const { fetchMock } = renderWithProviders(<div />, {
      routes: {
        "POST /api/v1/auth/logout": () => {
          attempts += 1;
          return attempts === 1
            ? problem(403, "csrf_failed", "Request blocked")
            : new Response(null, { status: 204 });
        },
      },
    });
    const result = await browserApi.POST("/api/v1/auth/logout");
    expect(result.response.status).toBe(204);
    expect(attempts).toBe(2);
    expect(
      fetchMock.mock.calls.some(([r]) =>
        String(r instanceof Request ? r.url : r).endsWith("/auth/csrf"),
      ),
    ).toBe(true);
  });
});
