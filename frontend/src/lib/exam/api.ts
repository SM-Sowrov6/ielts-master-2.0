/**
 * Candidate Listening API (/api/v1/listening/*, /api/v1/attempts/*). The backend owns timing,
 * scoring and answer keys; nothing here can change a result.
 */

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import type { ExamModule } from "@/lib/exam/module";

type S = components["schemas"];
export type ListeningTest = S["ListeningTestOut"];
export type ListeningTestDetail = S["ListeningTestDetailOut"];
export type Attempt = S["AttemptOut"];
export type Lease = S["LeaseOut"];
export type StoredAnswer = S["StoredAnswerOut"];
export type SaveAnswersResult = S["SaveAnswersOut"];
export type AnswerItem = S["AnswerItemIn"];
export type Audio = S["AudioOut"];
export type Result = S["ResultOut"];
export type Review = S["AttemptReviewOut"];
export type ReviewItem = S["ReviewItemOut"];
export type Mode = "practice" | "exam";

/** Key-stripped content of an attempt (handler student views). */
export type Option = { label: string; text: string };
export type ContentQuestion = {
  id: string;
  number_from: number;
  number_to: number;
  marks: number;
  stem: unknown;
  options?: Option[];
};
export type ContentGroup = {
  question_type: string;
  instructions: string | null;
  answer_format: "option" | "options" | "text";
  config: Record<string, unknown>;
  options: Option[];
  questions: ContentQuestion[];
  has_image: boolean;
};
export type Paragraph = { label: string | null; text: string };
export type Passage = { title: string | null; body: unknown; paragraphs: Paragraph[] };
export type ContentSection = {
  section_no: number;
  passages?: Passage[];
  title: string | null;
  context: string | null;
  instructions: string | null;
  has_audio: boolean;
  groups: ContentGroup[];
};
export type AttemptContent = {
  version_id: string;
  module?: ExamModule;
  duration_seconds: number | null;
  sections: ContentSection[];
};
export type Response = { text: string } | { choice: string } | { choices: string[] } | null;

export async function fetchListeningTests(
  query: { search?: string; difficulty?: "easy" | "medium" | "hard" },
  module: ExamModule = "listening",
): Promise<ListeningTest[]> {
  return unwrap(
    await browserApi.GET("/api/v1/{module}/tests", {
      cache: "no-store",
      params: {
        path: { module },
        query: { search: query.search || undefined, difficulty: query.difficulty },
      },
    }),
  );
}

export async function fetchListeningTest(
  testId: string,
  module: ExamModule = "listening",
): Promise<ListeningTestDetail> {
  return unwrap(
    await browserApi.GET("/api/v1/{module}/tests/{test_id}", {
      cache: "no-store",
      params: { path: { module, test_id: testId } },
    }),
  );
}

export async function createAttempt(
  testId: string,
  mode: Mode,
  idempotencyKey: string,
  module: ExamModule = "listening",
): Promise<Attempt> {
  return unwrap(
    await browserApi.POST("/api/v1/attempts", {
      body: { test_id: testId, mode, module },
      params: { header: { "Idempotency-Key": idempotencyKey } },
    }),
  );
}

export async function fetchAttempt(attemptId: string): Promise<Attempt> {
  return unwrap(
    await browserApi.GET("/api/v1/attempts/{attempt_id}", {
      cache: "no-store",
      params: { path: { attempt_id: attemptId } },
    }),
  );
}

export async function fetchHistory(testId?: string, module?: ExamModule): Promise<Attempt[]> {
  return unwrap(
    await browserApi.GET("/api/v1/attempts", {
      cache: "no-store",
      params: { query: { test_id: testId, module } },
    }),
  ).items;
}

export async function startAttempt(attemptId: string): Promise<Lease> {
  return unwrap(
    await browserApi.POST("/api/v1/attempts/{attempt_id}/start", {
      params: { path: { attempt_id: attemptId } },
    }),
  );
}

export async function resumeAttempt(attemptId: string): Promise<Lease> {
  return unwrap(
    await browserApi.POST("/api/v1/attempts/{attempt_id}/resume", {
      params: { path: { attempt_id: attemptId } },
    }),
  );
}

export async function fetchContent(attemptId: string): Promise<AttemptContent> {
  const data = unwrap(
    await browserApi.GET("/api/v1/attempts/{attempt_id}/content", {
      cache: "no-store",
      params: { path: { attempt_id: attemptId } },
    }),
  );
  return data as unknown as AttemptContent;
}

export async function fetchAnswers(attemptId: string): Promise<S["AnswersOut"]> {
  return unwrap(
    await browserApi.GET("/api/v1/attempts/{attempt_id}/answers", {
      cache: "no-store",
      params: { path: { attempt_id: attemptId } },
    }),
  );
}

export async function putAnswers(
  attemptId: string,
  lease: { epoch: number; token: string },
  answers: AnswerItem[],
): Promise<SaveAnswersResult> {
  return unwrap(
    await browserApi.PUT("/api/v1/attempts/{attempt_id}/answers", {
      params: { path: { attempt_id: attemptId }, header: { "X-Writer-Token": lease.token } },
      body: { writer_epoch: lease.epoch, answers },
    }),
  );
}

export async function submitAttempt(
  attemptId: string,
  lease: { epoch: number; token: string },
  idempotencyKey: string,
  finalAnswers: AnswerItem[],
): Promise<Attempt> {
  return unwrap(
    await browserApi.POST("/api/v1/attempts/{attempt_id}/submit", {
      params: {
        path: { attempt_id: attemptId },
        header: { "Idempotency-Key": idempotencyKey, "X-Writer-Token": lease.token },
      },
      body: { writer_epoch: lease.epoch, final_answers: finalAnswers },
    }),
  );
}

export async function fetchAudio(attemptId: string, sectionNo: number): Promise<Audio> {
  return unwrap(
    await browserApi.POST("/api/v1/attempts/{attempt_id}/sections/{section_no}/audio-url", {
      params: { path: { attempt_id: attemptId, section_no: sectionNo } },
    }),
  );
}

export async function fetchImage(
  attemptId: string,
  sectionNo: number,
  groupNo: number,
): Promise<S["ImageOut"]> {
  return unwrap(
    await browserApi.GET(
      "/api/v1/attempts/{attempt_id}/sections/{section_no}/groups/{group_no}/image-url",
      {
        cache: "no-store",
        params: { path: { attempt_id: attemptId, section_no: sectionNo, group_no: groupNo } },
      },
    ),
  );
}

export async function fetchResult(attemptId: string): Promise<Result> {
  return unwrap(
    await browserApi.GET("/api/v1/attempts/{attempt_id}/result", {
      cache: "no-store",
      params: { path: { attempt_id: attemptId } },
    }),
  );
}

export async function fetchReview(attemptId: string): Promise<Review> {
  return unwrap(
    await browserApi.GET("/api/v1/attempts/{attempt_id}/review", {
      cache: "no-store",
      params: { path: { attempt_id: attemptId } },
    }),
  );
}
