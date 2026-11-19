import { describe, expect, it } from "vitest";

import { ApiError, unwrap } from "@/lib/api/errors";

const response = (status: number) => new Response(null, { status });

describe("ApiError / unwrap", () => {
  it("returns data for successful responses", () => {
    expect(unwrap({ data: { status: "ok" }, response: response(200) })).toEqual({ status: "ok" });
  });

  it("maps problem+json to a typed error with the stable code and request id", () => {
    const problem = {
      type: "urn:ielts-master:problem:not_found",
      title: "Not Found",
      status: 404,
      code: "not_found",
      request_id: "req-1",
    };
    let caught: unknown;
    try {
      unwrap({ error: problem, response: response(404) });
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(ApiError);
    const apiError = caught as ApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.code).toBe("not_found");
    expect(apiError.requestId).toBe("req-1");
    expect(apiError.isClientError).toBe(true);
  });

  it("falls back to a generic code when the body is not problem+json", () => {
    const error = (() => {
      try {
        unwrap({ error: "<html>bad gateway</html>", response: response(502) });
      } catch (e) {
        return e as ApiError;
      }
    })();
    expect(error?.code).toBe("internal_error");
    expect(error?.isClientError).toBe(false);
  });
});
