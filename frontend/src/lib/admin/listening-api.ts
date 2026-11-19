/**
 * Browser calls for Super Admin Listening management (/api/v1/admin/content/*).
 * The backend authorises every call; nothing here decides access.
 */

import { browserApi } from "@/lib/api/client";
import { ApiError, ensureOk, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import type { AdminModule, ObjectiveModule } from "@/lib/admin/module";

type S = components["schemas"];
export type ListeningRow = S["ListeningRowOut"];
export type ListeningPage = S["ListeningPageOut"];
export type ListeningOverview = S["ListeningOverviewOut"];
export type EditorDocument = S["EditorDocumentOut"];
export type SaveResult = S["SaveResultOut"];
export type Issue = S["IssueOut"];
export type SectionDoc = S["SectionIn"];
export type GroupDoc = S["GroupIn"];
export type QuestionDoc = S["QuestionIn"];
export type OptionDoc = S["OptionIn"];
export type AnswerDoc = S["AnswerIn"];
export type Asset = S["AssetOut"];
export type Book = S["BookOut"];
export type Licence = S["LicenceOut"];
export type QuestionType = S["QuestionTypeOut"];
export type Preview = S["PreviewOut"];
export type SaveDraftInput = S["SaveListeningDraftIn"];
export type CreateTestInput = S["CreateListeningTestIn"];
export type ListStatus = NonNullable<ListeningRow["status"]>;
export type Difficulty = "easy" | "medium" | "hard";

const BASE = "/api/v1/admin/content";

/** Validation issues carried by a 422 `content_validation_failed` problem. */
export class ContentValidationError extends ApiError {
  readonly issues: Issue[];

  constructor(error: ApiError, issues: Issue[]) {
    super(error.status, { code: error.code, title: error.message, detail: error.detail });
    this.issues = issues;
  }
}

async function withIssues<T>(
  result: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const settled = await result;
  try {
    return unwrap(settled);
  } catch (error) {
    const issues = (settled.error as { issues?: Issue[] } | undefined)?.issues;
    if (error instanceof ApiError && Array.isArray(issues)) {
      throw new ContentValidationError(error, issues);
    }
    throw error;
  }
}

export type ListQuery = {
  search?: string;
  status?: ListStatus;
  difficulty?: Difficulty;
  offset: number;
  limit: number;
};

export async function fetchListeningOverview(
  module: AdminModule = "listening",
): Promise<ListeningOverview> {
  return unwrap(
    await browserApi.GET(`${BASE}/{module}/overview`, {
      cache: "no-store",
      params: { path: { module } },
    }),
  );
}

export async function fetchListeningTests(
  query: ListQuery,
  module: AdminModule = "listening",
): Promise<ListeningPage> {
  return unwrap(
    await browserApi.GET(`${BASE}/{module}/tests`, {
      cache: "no-store",
      params: {
        path: { module },
        query: {
          search: query.search || undefined,
          status: query.status,
          difficulty: query.difficulty,
          offset: query.offset,
          limit: query.limit,
        },
      },
    }),
  );
}

export async function fetchQuestionTypes(
  module: ObjectiveModule = "listening",
): Promise<QuestionType[]> {
  return unwrap(await browserApi.GET(`${BASE}/question-types`, { params: { query: { module } } }));
}

export async function fetchBooks(): Promise<Book[]> {
  return unwrap(await browserApi.GET(`${BASE}/books`, { cache: "no-store" }));
}

export async function fetchLicences(): Promise<Licence[]> {
  return unwrap(await browserApi.GET(`${BASE}/licences`, { cache: "no-store" }));
}

export async function createLicence(licensor: string): Promise<Licence> {
  return unwrap(await browserApi.POST(`${BASE}/licences`, { body: { licensor } }));
}

export async function createBook(body: S["BookCreateIn"]): Promise<Book> {
  return unwrap(await browserApi.POST(`${BASE}/books`, { body }));
}

export async function createEdition(
  bookId: string,
  body: S["EditionCreateIn"],
): Promise<S["EditionOut"]> {
  return unwrap(
    await browserApi.POST(`${BASE}/books/{book_id}/editions`, {
      params: { path: { book_id: bookId } },
      body,
    }),
  );
}

export async function createListeningTest(
  body: CreateTestInput,
  module: AdminModule = "listening",
): Promise<EditorDocument> {
  return withIssues(
    browserApi.POST(`${BASE}/{module}/tests`, { body, params: { path: { module } } }),
  );
}

export async function fetchEditorDocument(versionId: string): Promise<EditorDocument> {
  return unwrap(
    await browserApi.GET(`${BASE}/versions/{version_id}`, {
      cache: "no-store",
      params: { path: { version_id: versionId } },
    }),
  );
}

export async function saveDraft(versionId: string, body: SaveDraftInput): Promise<SaveResult> {
  return withIssues(
    browserApi.PUT(`${BASE}/versions/{version_id}`, {
      params: { path: { version_id: versionId } },
      body,
    }),
  );
}

export async function deleteDraft(versionId: string): Promise<void> {
  ensureOk(
    await browserApi.DELETE(`${BASE}/versions/{version_id}`, {
      params: { path: { version_id: versionId } },
    }),
  );
}

export async function fetchValidation(versionId: string): Promise<S["IssuesOut"]> {
  return unwrap(
    await browserApi.GET(`${BASE}/versions/{version_id}/validation`, {
      cache: "no-store",
      params: { path: { version_id: versionId } },
    }),
  );
}

export async function fetchPreview(versionId: string): Promise<Preview> {
  return unwrap(
    await browserApi.GET(`${BASE}/versions/{version_id}/preview`, {
      cache: "no-store",
      params: { path: { version_id: versionId } },
    }),
  );
}

type Action = "submit" | "publish" | "archive";

export async function runAction(versionId: string, action: Action): Promise<EditorDocument> {
  const path = { params: { path: { version_id: versionId } } };
  if (action === "submit") {
    return withIssues(browserApi.POST(`${BASE}/versions/{version_id}/submit`, path));
  }
  if (action === "publish") {
    return withIssues(browserApi.POST(`${BASE}/versions/{version_id}/publish`, path));
  }
  return withIssues(browserApi.POST(`${BASE}/versions/{version_id}/archive`, path));
}

export async function reviewVersion(
  versionId: string,
  decision: "approved" | "changes_requested",
  comment?: string,
): Promise<EditorDocument> {
  return unwrap(
    await browserApi.POST(`${BASE}/versions/{version_id}/review`, {
      params: { path: { version_id: versionId } },
      body: { decision, comment: comment || null },
    }),
  );
}

export async function duplicateTest(
  versionId: string,
  code: string,
  title: string,
): Promise<EditorDocument> {
  return unwrap(
    await browserApi.POST(`${BASE}/versions/{version_id}/duplicate`, {
      params: { path: { version_id: versionId } },
      body: { code, title },
    }),
  );
}

export async function newRevision(testId: string): Promise<EditorDocument> {
  return unwrap(
    await browserApi.POST(`${BASE}/tests/{test_id}/revisions`, {
      params: { path: { test_id: testId } },
    }),
  );
}

export async function fetchMediaUrl(assetId: string): Promise<S["MediaUrlOut"]> {
  return unwrap(
    await browserApi.GET(`${BASE}/media/{asset_id}/url`, {
      cache: "no-store",
      params: { path: { asset_id: assetId } },
    }),
  );
}

export async function startUpload(body: S["MediaUploadIn"]): Promise<S["MediaUploadOut"]> {
  return unwrap(await browserApi.POST(`${BASE}/media`, { body }));
}

export async function completeUpload(assetId: string): Promise<Asset> {
  return unwrap(
    await browserApi.POST(`${BASE}/media/{asset_id}/complete`, {
      params: { path: { asset_id: assetId } },
    }),
  );
}
