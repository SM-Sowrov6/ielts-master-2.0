import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { queryKeys } from "@/lib/query/keys";
import { makeQueryClient, shouldRetry } from "@/lib/query/query-client";

describe("query client conventions", () => {
  it("never retries client (4xx) errors", () => {
    expect(shouldRetry(0, new ApiError(422, { code: "validation_error" }))).toBe(false);
  });

  it("retries server and network errors at most twice", () => {
    const serverError = new ApiError(503, { code: "unavailable" });
    expect(shouldRetry(0, serverError)).toBe(true);
    expect(shouldRetry(1, new TypeError("network"))).toBe(true);
    expect(shouldRetry(2, serverError)).toBe(false);
  });

  it("does not retry mutations by default", () => {
    expect(makeQueryClient().getDefaultOptions().mutations?.retry).toBe(false);
  });

  it("builds hierarchical query keys under a domain root", () => {
    expect(queryKeys.system.readiness()).toEqual(["system", "readiness"]);
    expect(queryKeys.system.readiness().slice(0, 1)).toEqual([...queryKeys.system.all]);
  });
});
