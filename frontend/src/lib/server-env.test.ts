import { describe, expect, it } from "vitest";

import { readServerEnv, ServerEnvError } from "@/lib/server-env";

describe("readServerEnv", () => {
  it("returns the origin of a valid http(s) URL", () => {
    expect(readServerEnv({ API_INTERNAL_URL: "http://backend:8000/ignored/path" })).toEqual({
      apiInternalUrl: "http://backend:8000",
    });
  });

  it.each([
    [{}, "not set"],
    [{ API_INTERNAL_URL: "not a url" }, "not a valid URL"],
    [{ API_INTERNAL_URL: "ftp://backend" }, "http or https"],
  ])("rejects invalid configuration %#", (env, message) => {
    expect(() => readServerEnv(env)).toThrow(ServerEnvError);
    expect(() => readServerEnv(env)).toThrow(message);
  });
});
