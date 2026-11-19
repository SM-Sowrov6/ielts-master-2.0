import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvaluationView } from "@/components/practice/evaluation-view";
import { SpeakingTest } from "@/components/practice/speaking";
import { WritingExam, WritingSubmission, countWords } from "@/components/practice/writing";
import type { Evaluation, Submission } from "@/lib/practice/api";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const SID = "00000000-0000-7000-8000-0000000000a1";
const TID = "00000000-0000-7000-8000-0000000000b1";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

function evaluation(over: Partial<Evaluation> = {}): Evaluation {
  return {
    id: "e1",
    status: "succeeded",
    message: null,
    band_overall: 6.5,
    criteria: [
      {
        code: "TA",
        name: "Task response",
        band: 7,
        rationale: "Clear position.",
        strengths: ["Relevant ideas"],
        improvements: ["Develop examples"],
      },
      {
        code: "LR",
        name: "Lexical resource",
        band: 6,
        rationale: "Adequate range.",
        strengths: [],
        improvements: [],
      },
    ],
    feedback: [
      {
        kind: "grammar",
        excerpt: "more people",
        suggestion: "many more people",
        explanation: "Intensifier.",
      },
    ],
    summary: "A solid answer.",
    off_topic: false,
    improvement_plan: [],
    not_assessed: [],
    provider: "fake",
    model: "m",
    prompt_version: "1.0.0",
    retryable: false,
    created_at: "2026-11-19T10:00:00Z",
    finished_at: "2026-11-19T10:00:05Z",
    ...over,
  };
}

function submission(over: Partial<Submission> = {}): Submission {
  return {
    id: SID,
    test_id: TID,
    test_title: "Synthetic Writing",
    task_no: 2,
    task: {
      task_no: 2,
      task_kind: "essay",
      prompt_text: "Discuss transport.",
      min_words: 250,
      has_image: false,
      suggested_minutes: 40,
    },
    status: "draft",
    body: "",
    word_count: 0,
    client_revision: 0,
    time_spent_seconds: 0,
    created_at: "2026-11-19T10:00:00Z",
    updated_at: "2026-11-19T10:00:00Z",
    submitted_at: null,
    evaluation: null,
    model_answers: [],
    ...over,
  };
}

afterEach(() => {
  vi.useRealTimers();
  localStorage.clear();
});

describe("EvaluationView", () => {
  it("shows bands only for a succeeded evaluation", async () => {
    const { container, rerender } = renderWithProviders(
      <EvaluationView evaluation={evaluation()} retrying={false} onRetry={() => {}} />,
    );
    expect(screen.getByText("6.5")).toBeInTheDocument();
    expect(screen.getByText(/not an official IELTS score/)).toBeInTheDocument();
    expect(screen.getByText("many more people")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);

    const onRetry = vi.fn();
    rerender(
      <EvaluationView
        evaluation={evaluation({
          status: "unavailable",
          band_overall: null,
          criteria: [],
          feedback: [],
          summary: null,
          retryable: true,
          message: "AI evaluation is not available yet: no AI provider is configured.",
        })}
        retrying={false}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("no AI provider is configured");
    expect(screen.queryByText("6.5")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Try the assessment again/ }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("never invents a pronunciation band", () => {
    renderWithProviders(
      <EvaluationView
        evaluation={evaluation({ band_overall: null, not_assessed: ["PR"] })}
        retrying={false}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByText(/PR could not be assessed/)).toBeInTheDocument();
    expect(screen.getByText(/never guessed from a transcript/)).toBeInTheDocument();
  });
});

describe("Writing editor", () => {
  it("counts words like the server", () => {
    expect(countWords("It's a well-known fact, isn't it? 42 cats.")).toBe(8);
  });

  it("autosaves with increasing revisions and submits with an idempotency key", async () => {
    const puts: { body: string; client_revision: number }[] = [];
    let current = submission();
    let submitKey: string | null = null;
    renderWithProviders(<WritingExam submissionId={SID} />, {
      routes: {
        [`GET /api/v1/writing/submissions/${SID}`]: () => json(current),
        [`PUT /api/v1/writing/submissions/${SID}`]: async (_init, request) => {
          const body = await request!.json();
          puts.push(body);
          return json(submission({ body: body.body, client_revision: body.client_revision }));
        },
        [`POST /api/v1/writing/submissions/${SID}/submit`]: async (_init, request) => {
          submitKey = request!.headers.get("Idempotency-Key");
          const body = await request!.json();
          current = submission({
            status: "submitted",
            body: body.body,
            word_count: 4,
            submitted_at: "2026-11-19T10:10:00Z",
            evaluation: evaluation({ status: "queued", band_overall: null, criteria: [] }),
          });
          return json(current);
        },
      },
    });
    const box = await screen.findByLabelText("Your response");
    fireEvent.change(box, { target: { value: "Cities need better transport" } });
    expect(screen.getByText("4")).toBeInTheDocument();
    await waitFor(() => expect(puts).toHaveLength(1), { timeout: 4000 });
    expect(puts[0]!.body).toBe("Cities need better transport");
    expect(puts[0]!.client_revision).toBeGreaterThan(0);
    await screen.findByText("All changes saved");

    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(screen.getByText(/fewer than the 250 required/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Submit for assessment/ }));
    // Submitted: the full-screen room hands over to the result page.
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/writing/submissions/${SID}`));
    expect(submitKey).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("shows a submitted response and its pending assessment on the result page", async () => {
    renderWithProviders(<WritingSubmission submissionId={SID} />, {
      routes: {
        [`GET /api/v1/writing/submissions/${SID}`]: () =>
          json(
            submission({
              status: "submitted",
              body: "Cities need better transport",
              word_count: 4,
              submitted_at: "2026-11-19T10:10:00Z",
              evaluation: evaluation({ status: "queued", band_overall: null, criteria: [] }),
            }),
          ),
      },
    });
    expect(await screen.findByText(/being assessed/)).toBeInTheDocument();
    expect(screen.getByText("Cities need better transport")).toBeInTheDocument();
  });

  it("restores a longer local copy after a lost autosave", async () => {
    localStorage.setItem(`writing-draft:${SID}`, "Text typed while offline");
    renderWithProviders(<WritingExam submissionId={SID} />, {
      routes: { [`GET /api/v1/writing/submissions/${SID}`]: () => json(submission()) },
    });
    expect(await screen.findByLabelText("Your response")).toHaveValue("Text typed while offline");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });
});

describe("Speaking consent", () => {
  it("cannot start without both explicit consents", async () => {
    vi.stubGlobal(
      "MediaRecorder",
      Object.assign(function MediaRecorder() {}, { isTypeSupported: () => true }),
    );
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn() },
      configurable: true,
    });
    renderWithProviders(<SpeakingTest testId={TID} />, {
      routes: {
        [`GET /api/v1/speaking/tests/${TID}`]: () =>
          json({
            test: {
              test_id: TID,
              code: "S1",
              title: "Synthetic Speaking",
              description: null,
              difficulty: null,
              tags: [],
              book_title: "B",
              published_at: null,
            },
            parts: [
              {
                part_no: 1,
                topic: "Home",
                cue_card: null,
                questions: ["Where do you live?"],
                prep_seconds: 0,
                answer_seconds: 60,
              },
              {
                part_no: 2,
                topic: "Object",
                cue_card: { prompt: "Describe an object", points: [], closing: null },
                questions: [],
                prep_seconds: 60,
                answer_seconds: 120,
              },
            ],
            consent_version: "speaking-2026-11",
          }),
      },
    });
    const start = await screen.findByRole("button", { name: "Start speaking" });
    expect(start).toBeDisabled();
    const boxes = screen.getAllByRole("checkbox");
    await act(async () => {
      await userEvent.click(boxes[0]!);
    });
    expect(start).toBeDisabled();
    await userEvent.click(boxes[1]!);
    expect(start).toBeEnabled();
  });
});
