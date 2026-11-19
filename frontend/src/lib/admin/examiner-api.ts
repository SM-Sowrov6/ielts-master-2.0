/** Admin AI Examiner Configuration API (/api/v1/admin/speaking). Authorised on the server. */

import { browserApi } from "@/lib/api/client";
import { ensureOk, unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type ExaminerProfile = S["ProfileOut"];
export type ProfileInput = S["ProfileIn"];
export type ExaminerConfig = S["ConfigOut"];
export type ExaminerConfigBody = S["ExaminerConfigBody"];
export type ExaminerPreview = S["ExaminerPreviewOut"];

const BASE = "/api/v1/admin/speaking";
const cfg = (id: string) => ({ params: { path: { config_id: id } } });

export async function fetchProfiles(): Promise<ExaminerProfile[]> {
  return unwrap(await browserApi.GET(`${BASE}/examiners`, { cache: "no-store" }));
}

export async function updateProfile(id: string, body: ProfileInput): Promise<ExaminerProfile> {
  return unwrap(
    await browserApi.PUT(`${BASE}/examiners/{profile_id}`, {
      params: { path: { profile_id: id } },
      body,
    }),
  );
}

export async function fetchSpeakingTestOptions(): Promise<S["SpeakingTestOptionOut"][]> {
  return unwrap(await browserApi.GET(`${BASE}/tests`, { cache: "no-store" }));
}

export async function fetchConfigs(): Promise<ExaminerConfig[]> {
  return unwrap(await browserApi.GET(`${BASE}/configs`, { cache: "no-store" }));
}

export async function fetchConfig(id: string): Promise<ExaminerConfig> {
  return unwrap(
    await browserApi.GET(`${BASE}/configs/{config_id}`, { cache: "no-store", ...cfg(id) }),
  );
}

export async function createConfig(testId: string): Promise<ExaminerConfig> {
  return unwrap(await browserApi.POST(`${BASE}/configs`, { body: { test_id: testId } }));
}

export async function saveConfig(
  id: string,
  revision: string,
  body: ExaminerConfigBody,
): Promise<ExaminerConfig> {
  return unwrap(
    await browserApi.PUT(`${BASE}/configs/{config_id}`, { ...cfg(id), body: { revision, body } }),
  );
}

export async function deleteConfig(id: string): Promise<void> {
  ensureOk(await browserApi.DELETE(`${BASE}/configs/{config_id}`, cfg(id)));
}

export async function fetchPreview(id: string): Promise<ExaminerPreview> {
  return unwrap(
    await browserApi.GET(`${BASE}/configs/{config_id}/preview`, { cache: "no-store", ...cfg(id) }),
  );
}

export async function setPublished(id: string, publish: boolean): Promise<ExaminerConfig> {
  return publish
    ? unwrap(await browserApi.POST(`${BASE}/configs/{config_id}/publish`, cfg(id)))
    : unwrap(await browserApi.POST(`${BASE}/configs/{config_id}/unpublish`, cfg(id)));
}
