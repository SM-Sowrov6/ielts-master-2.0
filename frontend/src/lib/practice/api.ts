/**
 * Candidate Writing and Speaking API calls (/api/v1/writing, /api/v1/speaking). Owner-only on the
 * server; scores come only from the background evaluation job.
 */

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type WritingTest = S["WritingTestOut"];
export type WritingTestDetail = S["WritingTestDetailOut"];
export type Submission = S["SubmissionOut"];
export type SubmissionSummary = S["SubmissionSummaryOut"];
export type Evaluation = S["EvaluationOut"];
export type SpeakingTest = S["SpeakingTestOut"];
export type SpeakingTestDetail = S["SpeakingTestDetailOut"];
export type SpeakingSession = S["SessionOut"];
export type SessionSummary = S["SessionSummaryOut"];
export type SpeakingItem = S["ItemOut"];
export type SpeakingMode = "full" | "part1" | "part2" | "part3";

const key = () => ({ "Idempotency-Key": crypto.randomUUID() });

// ------------------------------------------------------------------------------ writing
export async function fetchWritingTests(): Promise<WritingTest[]> {
  return unwrap(await browserApi.GET("/api/v1/writing/tests", { cache: "no-store" }));
}

export async function fetchWritingTest(testId: string): Promise<WritingTestDetail> {
  return unwrap(
    await browserApi.GET("/api/v1/writing/tests/{test_id}", {
      cache: "no-store",
      params: { path: { test_id: testId } },
    }),
  );
}

export async function fetchTaskImage(testId: string, taskNo: number): Promise<string> {
  const out = unwrap(
    await browserApi.GET("/api/v1/writing/tests/{test_id}/tasks/{task_no}/image", {
      cache: "no-store",
      params: { path: { test_id: testId, task_no: taskNo } },
    }),
  );
  return out.url;
}

export async function startSubmission(testId: string, taskNo: 1 | 2): Promise<Submission> {
  return unwrap(
    await browserApi.POST("/api/v1/writing/submissions", {
      body: { test_id: testId, task_no: taskNo },
    }),
  );
}

export async function fetchSubmissions(): Promise<SubmissionSummary[]> {
  return unwrap(await browserApi.GET("/api/v1/writing/submissions", { cache: "no-store" }));
}

export async function fetchSubmission(id: string): Promise<Submission> {
  return unwrap(
    await browserApi.GET("/api/v1/writing/submissions/{submission_id}", {
      cache: "no-store",
      params: { path: { submission_id: id } },
    }),
  );
}

export type TextBody = { body: string; client_revision: number; time_spent_seconds: number };

export async function autosaveSubmission(id: string, body: TextBody): Promise<Submission> {
  return unwrap(
    await browserApi.PUT("/api/v1/writing/submissions/{submission_id}", {
      params: { path: { submission_id: id } },
      body,
    }),
  );
}

export async function submitSubmission(
  id: string,
  body: TextBody,
  idempotencyKey: string,
): Promise<Submission> {
  return unwrap(
    await browserApi.POST("/api/v1/writing/submissions/{submission_id}/submit", {
      params: { path: { submission_id: id }, header: { "Idempotency-Key": idempotencyKey } },
      body,
    }),
  );
}

export async function retryWritingEvaluation(id: string): Promise<Submission> {
  return unwrap(
    await browserApi.POST("/api/v1/writing/submissions/{submission_id}/evaluations", {
      params: { path: { submission_id: id }, header: key() },
    }),
  );
}

// ------------------------------------------------------------------------------ speaking
export async function fetchSpeakingTests(): Promise<SpeakingTest[]> {
  return unwrap(await browserApi.GET("/api/v1/speaking/tests", { cache: "no-store" }));
}

export async function fetchSpeakingTest(testId: string): Promise<SpeakingTestDetail> {
  return unwrap(
    await browserApi.GET("/api/v1/speaking/tests/{test_id}", {
      cache: "no-store",
      params: { path: { test_id: testId } },
    }),
  );
}

export async function startSpeakingSession(
  testId: string,
  mode: SpeakingMode,
): Promise<SpeakingSession> {
  return unwrap(
    await browserApi.POST("/api/v1/speaking/sessions", {
      body: {
        test_id: testId,
        mode,
        voice_processing_consent: true,
        audio_recording_consent: true,
      },
    }),
  );
}

export async function fetchSpeakingSessions(): Promise<SessionSummary[]> {
  return unwrap(await browserApi.GET("/api/v1/speaking/sessions", { cache: "no-store" }));
}

export async function fetchSpeakingSession(id: string): Promise<SpeakingSession> {
  return unwrap(
    await browserApi.GET("/api/v1/speaking/sessions/{session_id}", {
      cache: "no-store",
      params: { path: { session_id: id } },
    }),
  );
}

async function sha256Hex(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Upload one answer: presigned PUT straight to storage, then server-side verification. */
export async function uploadRecording(
  sessionId: string,
  item: { part_no: 1 | 2 | 3; question_no: number },
  blob: Blob,
  durationMs: number,
): Promise<void> {
  const ticket = unwrap(
    await browserApi.POST("/api/v1/speaking/sessions/{session_id}/recordings", {
      params: { path: { session_id: sessionId } },
      body: {
        part_no: item.part_no,
        question_no: item.question_no,
        mime_type: blob.type || "audio/webm",
        size_bytes: blob.size,
        sha256: await sha256Hex(blob),
        duration_ms: Math.max(1, Math.round(durationMs)),
      },
    }),
  );
  const put = await fetch(ticket.upload_url, {
    method: "PUT",
    body: blob,
    headers: ticket.headers,
  });
  if (!put.ok) throw new Error("The recording could not be uploaded. Please try again.");
  unwrap(
    await browserApi.POST(
      "/api/v1/speaking/sessions/{session_id}/recordings/{recording_id}/complete",
      {
        params: { path: { session_id: sessionId, recording_id: ticket.recording_id } },
      },
    ),
  );
}

export async function fetchRecordingUrl(sessionId: string, recordingId: string): Promise<string> {
  const out = unwrap(
    await browserApi.GET("/api/v1/speaking/sessions/{session_id}/recordings/{recording_id}/url", {
      cache: "no-store",
      params: { path: { session_id: sessionId, recording_id: recordingId } },
    }),
  );
  return out.url;
}

export async function submitSpeakingSession(
  id: string,
  idempotencyKey: string,
): Promise<SpeakingSession> {
  return unwrap(
    await browserApi.POST("/api/v1/speaking/sessions/{session_id}/submit", {
      params: { path: { session_id: id }, header: { "Idempotency-Key": idempotencyKey } },
    }),
  );
}

export async function retrySpeakingEvaluation(id: string): Promise<SpeakingSession> {
  return unwrap(
    await browserApi.POST("/api/v1/speaking/sessions/{session_id}/evaluations", {
      params: { path: { session_id: id }, header: key() },
    }),
  );
}

export const isPending = (e: Evaluation | null | undefined) =>
  e?.status === "queued" || e?.status === "running";
