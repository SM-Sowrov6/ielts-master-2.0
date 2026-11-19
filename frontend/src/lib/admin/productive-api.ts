/**
 * Browser calls for Super Admin Writing/Speaking management and rubric versions
 * (/api/v1/admin/content/*). The backend authorises every call.
 */

import { browserApi } from "@/lib/api/client";
import { ensureOk, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import {
  ContentValidationError,
  type EditorDocument,
  type SaveResult,
} from "@/lib/admin/listening-api";
import { ApiError } from "@/lib/api/errors";

type S = components["schemas"];
export type WritingTaskDoc = S["WritingTaskIn"];
export type SpeakingPartDoc = S["SpeakingPartIn"];
export type ModelAnswerDoc = S["ModelAnswerIn"];
export type SaveProductiveInput = S["SaveProductiveDraftIn"];
export type Rubric = S["RubricOut"];
export type RubricCriterion = S["CriterionIn"];
export type RubricModule = "writing" | "speaking";

const BASE = "/api/v1/admin/content";

async function withIssues<T>(
  result: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const settled = await result;
  try {
    return unwrap(settled);
  } catch (error) {
    const issues = (settled.error as { issues?: [] } | undefined)?.issues;
    if (error instanceof ApiError && Array.isArray(issues)) {
      throw new ContentValidationError(error, issues);
    }
    throw error;
  }
}

export async function saveProductiveDraft(
  versionId: string,
  body: SaveProductiveInput,
): Promise<SaveResult> {
  return withIssues(
    browserApi.PUT(`${BASE}/versions/{version_id}/productive`, {
      params: { path: { version_id: versionId } },
      body,
    }),
  );
}

export function productiveBody(
  doc: EditorDocument,
  patch: Partial<SaveProductiveInput>,
): SaveProductiveInput {
  return {
    revision: doc.version.revision,
    title: doc.test.title,
    description: doc.version.description,
    difficulty: doc.version.difficulty,
    tags: doc.version.tags,
    duration_seconds: doc.duration_seconds,
    admin_notes: doc.test.admin_notes,
    change_note: doc.version.change_note,
    writing_tasks: doc.writing_tasks,
    speaking_parts: doc.speaking_parts,
    ...patch,
  };
}

export async function fetchRubrics(module: RubricModule): Promise<Rubric[]> {
  return unwrap(
    await browserApi.GET(`${BASE}/rubrics`, { cache: "no-store", params: { query: { module } } }),
  );
}

export async function fetchRubric(id: string): Promise<Rubric> {
  return unwrap(
    await browserApi.GET(`${BASE}/rubrics/{rubric_id}`, {
      cache: "no-store",
      params: { path: { rubric_id: id } },
    }),
  );
}

export async function createRubric(module: RubricModule): Promise<Rubric> {
  return unwrap(await browserApi.POST(`${BASE}/rubrics`, { body: { module } }));
}

export async function saveRubric(
  id: string,
  body: {
    revision: string;
    title: string;
    change_note: string | null;
    criteria: RubricCriterion[];
  },
): Promise<Rubric> {
  return withIssues(
    browserApi.PUT(`${BASE}/rubrics/{rubric_id}`, { params: { path: { rubric_id: id } }, body }),
  );
}

export async function deleteRubric(id: string): Promise<void> {
  ensureOk(
    await browserApi.DELETE(`${BASE}/rubrics/{rubric_id}`, {
      params: { path: { rubric_id: id } },
    }),
  );
}

export async function rubricAction(id: string, action: "submit" | "publish"): Promise<Rubric> {
  const path = { params: { path: { rubric_id: id } } };
  return action === "submit"
    ? withIssues(browserApi.POST(`${BASE}/rubrics/{rubric_id}/submit`, path))
    : unwrap(await browserApi.POST(`${BASE}/rubrics/{rubric_id}/publish`, path));
}

export async function reviewRubric(
  id: string,
  decision: "approved" | "changes_requested",
  comment?: string,
): Promise<Rubric> {
  return unwrap(
    await browserApi.POST(`${BASE}/rubrics/{rubric_id}/review`, {
      params: { path: { rubric_id: id } },
      body: { decision, comment: comment || null },
    }),
  );
}
