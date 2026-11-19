/**
 * RFC 9457 problem+json errors from the backend (docs/API_SPECIFICATION.md §1).
 * UI code branches on the stable `code`, never on `title`/`detail` text.
 */

export type ProblemDetails = {
  type: string;
  title: string;
  status: number;
  code: string;
  instance?: string;
  detail?: string;
  request_id?: string;
  errors?: { loc: (string | number)[]; msg: string; code: string }[];
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | undefined;
  readonly detail: string | undefined;
  readonly fieldErrors: ProblemDetails["errors"];

  constructor(status: number, problem: Partial<ProblemDetails> | undefined) {
    super(problem?.title ?? `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = problem?.code ?? (status >= 500 ? "internal_error" : "http_error");
    this.requestId = problem?.request_id;
    this.detail = problem?.detail;
    this.fieldErrors = problem?.errors;
  }

  /** 4xx errors are caller problems: retrying them cannot succeed. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }
}

function isProblem(value: unknown): value is Partial<ProblemDetails> {
  return typeof value === "object" && value !== null && ("code" in value || "title" in value);
}

/** Convert an openapi-fetch result into data or a thrown ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) {
    return result.data;
  }
  throw new ApiError(result.response.status, isProblem(result.error) ? result.error : undefined);
}

/** For endpoints without a response body (204/202 with ignored body): throw on failure. */
export function ensureOk(result: { error?: unknown; response: Response }): void {
  if (!result.response.ok) {
    throw new ApiError(result.response.status, isProblem(result.error) ? result.error : undefined);
  }
}
