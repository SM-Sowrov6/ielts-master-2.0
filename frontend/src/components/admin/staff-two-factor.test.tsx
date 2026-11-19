import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StaffTwoFactor } from "@/components/admin/staff-two-factor";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/admin" }));
vi.mock("qrcode", () => ({
  default: { toDataURL: () => Promise.resolve("data:image/png;base64,AA==") },
}));

const ok = (body: unknown = {}, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const problem = (status: number, code: string, title: string) =>
  new Response(JSON.stringify({ status, code, title }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
const status = (enrolled: boolean) => () =>
  ok({ enrolled, verified: false, required: true, recovery_codes_left: enrolled ? 10 : 0 });

beforeEach(() => vi.clearAllMocks());

describe("StaffTwoFactor", () => {
  it("enrols: QR code, confirm, recovery codes, then opens the console", async () => {
    const user = userEvent.setup();
    const codes = Array.from({ length: 10 }, (_, i) => `aaaa${i}-bbbbb`);
    const { container } = renderWithProviders(<StaffTwoFactor />, {
      routes: {
        "GET /api/v1/me/mfa": status(false),
        "POST /api/v1/me/mfa/totp/setup": () =>
          ok({ secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/IELTS%20MASTER:a" }),
        "POST /api/v1/me/mfa/totp/confirm": () => ok({ recovery_codes: codes }),
      },
    });
    await user.click(await screen.findByRole("button", { name: "Set up authenticator" }));
    expect(await screen.findByAltText("QR code for your authenticator app")).toBeInTheDocument();
    expect(screen.getByText("JBSW Y3DP EHPK 3PXP")).toBeInTheDocument();
    await user.type(screen.getByLabelText("6-digit code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm and continue" }));
    expect(await screen.findByText("aaaa0-bbbbb")).toBeInTheDocument();
    const open = screen.getByRole("button", { name: "Open the admin console" });
    expect(open).toBeDisabled();
    await user.click(screen.getByLabelText("I have saved my recovery codes"));
    await user.click(open);
    expect(router.refresh).toHaveBeenCalled();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("verifies with a code, shows errors, and offers recovery codes", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderWithProviders(<StaffTwoFactor />, {
      routes: {
        "GET /api/v1/me/mfa": status(true),
        "POST /api/v1/me/mfa/verify": () =>
          ++attempts === 1
            ? problem(400, "mfa_code_invalid", "That code is not valid.")
            : new Response(null, { status: 204 }),
      },
    });
    const input = await screen.findByLabelText("6-digit code from your authenticator app");
    await user.type(input, "111111");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That code is not valid.");
    await user.click(screen.getByRole("button", { name: /use a recovery code/i }));
    await user.type(screen.getByLabelText("Recovery code"), "abcde-12345");
    await user.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
  });
});
