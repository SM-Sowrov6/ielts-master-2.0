import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AttemptResult } from "@/components/listening/attempt-result";
import { AudioPlayer } from "@/components/listening/audio-player";
import { ExamRoom } from "@/components/listening/exam-room";
import { ListeningHome } from "@/components/listening/listening-home";
import { QuestionGroup } from "@/components/listening/question-group";
import { TestIntro } from "@/components/listening/test-intro";
import { textToDoc } from "@/lib/admin/richtext";
import { AnswerQueue, rememberLease, storedLease } from "@/lib/exam/answer-queue";
import type { ContentGroup, Response as AnswerResponse } from "@/lib/exam/api";
import { formatClock, isAnswered, remainingMs } from "@/lib/exam/responses";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/listening", useRouter: () => router }));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });
type Handler = (init?: RequestInit, request?: Request) => Response | Promise<Response>;

const AID = "00000000-0000-7000-8000-0000000000a1";
const TID = "00000000-0000-7000-8000-0000000000t1".replace("t", "e");
const q = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `q${n}`,
  number_from: n,
  number_to: n,
  marks: 1,
  stem: textToDoc(`Synthetic prompt ${n} ____`),
  ...extra,
});
const letters = (s: string) => [...s].map((l) => ({ label: l, text: `Synthetic ${l}` }));

/** One group per family/layout; together they cover the 13 Listening type codes. */
const GROUPS: Record<string, ContentGroup> = {
  form_completion: {
    question_type: "form_completion",
    instructions: "Write ONE WORD.",
    answer_format: "text",
    config: { word_limit: 1 },
    options: [],
    questions: [q(1)],
    has_image: false,
  },
  mcq_single: {
    question_type: "mcq_single",
    instructions: "Choose A, B or C.",
    answer_format: "option",
    config: {},
    options: [],
    questions: [q(2, { options: letters("ABC") })],
    has_image: false,
  },
  matching_features: {
    question_type: "matching_features",
    instructions: "Match.",
    answer_format: "option",
    config: {},
    options: letters("ABC"),
    questions: [q(3)],
    has_image: false,
  },
  mcq_multi: {
    question_type: "mcq_multi",
    instructions: "Choose TWO.",
    answer_format: "options",
    config: {},
    options: letters("ABCDE"),
    questions: [{ ...q(4), number_to: 5, marks: 2 }],
    has_image: false,
  },
  summary_completion: {
    question_type: "summary_completion",
    instructions: "Word bank.",
    answer_format: "option",
    config: {},
    options: letters("ABCD"),
    questions: [q(6)],
    has_image: false,
  },
  note_completion: {
    question_type: "note_completion",
    instructions: "Complete the notes.",
    answer_format: "text",
    config: {
      word_limit: 2,
      template: {
        type: "doc",
        content: [
          {
            type: "paragraph",
            content: [
              { type: "text", text: "Opening day: " },
              { type: "blank", attrs: { number: 7 } },
            ],
          },
        ],
      },
    },
    options: [],
    questions: [q(7)],
    has_image: false,
  },
};
const TEXT_TYPES = [
  "table_completion",
  "flowchart_completion",
  "sentence_completion",
  "short_answer",
  "plan_labelling",
  "diagram_labelling",
];

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  document.documentElement.lang = "en";
  document.title = "Listening · IELTS MASTER 2.0";
});
afterEach(() => vi.useRealTimers());

function renderGroup(group: ContentGroup, answers: Record<string, AnswerResponse> = {}) {
  const onChange = vi.fn();
  const view = renderWithProviders(
    <QuestionGroup
      group={group}
      answers={answers}
      onChange={onChange}
      disabled={false}
      attemptId={AID}
      sectionNo={1}
      groupNo={1}
    />,
  );
  return { ...view, onChange };
}

// ------------------------------------------------------------------------------ renderers
describe("QuestionGroup renderers (all 13 Listening types)", () => {
  it("typed answers send {text} and warn about the word limit", () => {
    const { onChange } = renderGroup(GROUPS.form_completion!, { q1: { text: "two words" } });
    expect(
      screen.getByText(/More than 1 word: an answer over the limit scores zero/),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Question 1" }), {
      target: { value: "lamp" },
    });
    expect(onChange).toHaveBeenCalledWith("q1", { text: "lamp" });
    fireEvent.change(screen.getByRole("textbox", { name: "Question 1" }), {
      target: { value: "" },
    });
    expect(onChange).toHaveBeenLastCalledWith("q1", null);
  });

  it.each(TEXT_TYPES)("%s renders a text answer box", (type) => {
    const { onChange } = renderGroup({ ...GROUPS.form_completion!, question_type: type });
    fireEvent.change(screen.getByRole("textbox", { name: "Question 1" }), {
      target: { value: "valve" },
    });
    expect(onChange).toHaveBeenCalledWith("q1", { text: "valve" });
  });

  it("per-question options use radio buttons and send {choice}", async () => {
    const user = userEvent.setup();
    const { onChange, container } = renderGroup(GROUPS.mcq_single!);
    await user.click(screen.getByRole("radio", { name: /B Synthetic B/ }));
    expect(onChange).toHaveBeenCalledWith("q2", { choice: "B" });
    expect(await axeViolations(container)).toEqual([]);
  });

  it.each(["matching_features", "map_labelling", "summary_completion"])(
    "%s shows the shared options once and a choice per question",
    (type) => {
      const base =
        type === "summary_completion" ? GROUPS.summary_completion! : GROUPS.matching_features!;
      const { onChange } = renderGroup({ ...base, question_type: type });
      expect(screen.getByText("Options")).toBeInTheDocument();
      const select = screen.getByRole("combobox");
      fireEvent.change(select, { target: { value: "A" } });
      expect(onChange).toHaveBeenCalledWith(base.questions[0]!.id, { choice: "A" });
      fireEvent.change(select, { target: { value: "" } });
      expect(onChange).toHaveBeenLastCalledWith(base.questions[0]!.id, null);
    },
  );

  it("choose-N questions send sorted {choices} and stop at the number of marks", async () => {
    const user = userEvent.setup();
    const { onChange, rerender } = renderGroup(GROUPS.mcq_multi!, { q4: { choices: ["D"] } });
    await user.click(screen.getByRole("checkbox", { name: /A Synthetic A/ }));
    expect(onChange).toHaveBeenCalledWith("q4", { choices: ["A", "D"] });
    rerender(
      <QuestionGroup
        group={GROUPS.mcq_multi!}
        answers={{ q4: { choices: ["A", "D"] } }}
        onChange={onChange}
        disabled={false}
        attemptId={AID}
        sectionNo={1}
        groupNo={1}
      />,
    );
    expect(screen.getByRole("checkbox", { name: /B Synthetic B/ })).toBeDisabled(); // 2 of 2 chosen
    expect(screen.getByText("Choose 2 (2 selected)")).toBeInTheDocument();
  });

  it("completion templates place answer boxes at the numbered blanks", () => {
    const { onChange } = renderGroup(GROUPS.note_completion!);
    expect(screen.getByText("Opening day:")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "monday" } });
    expect(onChange).toHaveBeenCalledWith("q7", { text: "monday" });
  });

  it("locks every input when the attempt is closed", () => {
    renderWithProviders(
      <QuestionGroup
        group={GROUPS.mcq_single!}
        answers={{}}
        onChange={vi.fn()}
        disabled
        attemptId={AID}
        sectionNo={1}
        groupNo={1}
      />,
    );
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });
});

// ------------------------------------------------------------------------------ autosave
describe("AnswerQueue", () => {
  const lease = { epoch: 1, token: "tok-0123456789" };

  it("debounces, sends the newest revision and clears acknowledged answers", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const bodies: { answers: { question_id: string; client_revision: number }[] }[] = [];
    renderWithProviders(<div />, {
      routes: {
        [`PUT /api/v1/attempts/${AID}/answers`]: async (_i, r) => {
          const body = (await r!.clone().json()) as (typeof bodies)[number];
          bodies.push(body);
          return json({
            stored: body.answers.map((a) => ({
              ...a,
              writer_epoch: 1,
              flagged: false,
              saved_at: "2026-11-19T10:00:00Z",
              response: {},
            })),
            server_now: "2026-11-19T10:00:00Z",
            deadline_at: null,
          });
        },
      },
    });
    const states: string[] = [];
    const queue = new AnswerQueue(AID, lease, {
      onState: (s) => states.push(s),
      onServerTime: () => {},
      onFatal: () => {},
    });
    queue.set("q1", { text: "l" });
    queue.set("q1", { text: "li" });
    queue.set("q1", { text: "library" });
    expect(queue.hasPending()).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });
    await waitFor(() => expect(states.at(-1)).toBe("saved"));
    expect(bodies).toHaveLength(1); // debounced into one request
    expect(bodies[0]!.answers[0]!.client_revision).toBe(3);
    expect(queue.hasPending()).toBe(false);
  });

  it("persists unacknowledged answers with the lease and replays them after a reload", async () => {
    rememberLease(AID, 1, lease.token);
    renderWithProviders(<div />, {
      routes: {
        [`PUT /api/v1/attempts/${AID}/answers`]: () =>
          json({ code: "internal_error", title: "x" }, 503),
      },
    });
    const first = new AnswerQueue(AID, lease, {
      onState: () => {},
      onServerTime: () => {},
      onFatal: () => {},
    });
    first.set("q2", { choice: "B" });
    first.stop(); // tab closed before the save went out
    expect(storedLease(AID)).toEqual(lease);
    const reopened = new AnswerQueue(AID, lease, {
      onState: () => {},
      onServerTime: () => {},
      onFatal: () => {},
    });
    expect(reopened.pendingAnswers()).toEqual({ q2: { choice: "B" } });
    expect(reopened.finalItems()[0]).toMatchObject({ question_id: "q2", client_revision: 1 });
    reopened.set("q2", { choice: "C" });
    expect(reopened.finalItems()[0]!.client_revision).toBe(2); // revisions keep increasing
  });

  it("retries server errors with backoff and stops on fatal responses", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    const fatal = vi.fn();
    const states: string[] = [];
    renderWithProviders(<div />, {
      routes: {
        [`PUT /api/v1/attempts/${AID}/answers`]: () => {
          calls += 1;
          return calls === 1
            ? json({ code: "internal_error", title: "x" }, 503)
            : json({ code: "superseded_session", title: "Continued elsewhere" }, 409);
        },
      },
    });
    const queue = new AnswerQueue(AID, lease, {
      onState: (s) => states.push(s),
      onServerTime: () => {},
      onFatal: fatal,
    });
    queue.set("q1", { text: "x" });
    await act(async () => {
      await queue.flush();
    });
    expect(states).toContain("retrying");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    await waitFor(() => expect(fatal).toHaveBeenCalledWith("superseded_session"));
    expect(states.at(-1)).toBe("stopped");
    queue.set("q1", { text: "ignored" });
    expect(calls).toBe(2);
  });

  it("isolates a rejected answer instead of dropping the whole batch", async () => {
    const saved: string[] = [];
    renderWithProviders(<div />, {
      routes: {
        [`PUT /api/v1/attempts/${AID}/answers`]: async (_i, r) => {
          const body = (await r!.clone().json()) as {
            answers: { question_id: string; client_revision: number }[];
          };
          if (body.answers.some((a) => a.question_id === "bad"))
            return json({ code: "response_invalid", title: "x" }, 422);
          saved.push(...body.answers.map((a) => a.question_id));
          return json({
            stored: body.answers.map((a) => ({
              ...a,
              writer_epoch: 1,
              flagged: false,
              saved_at: "x",
              response: {},
            })),
            server_now: "2026-11-19T10:00:00Z",
            deadline_at: null,
          });
        },
      },
    });
    const queue = new AnswerQueue(AID, lease, {
      onState: () => {},
      onServerTime: () => {},
      onFatal: () => {},
    });
    queue.set("good1", { text: "a" });
    queue.set("bad", { text: "b" });
    queue.set("good2", { text: "c" });
    await act(async () => {
      await queue.flush();
    });
    expect(saved.sort()).toEqual(["good1", "good2"]);
    expect(queue.hasPending()).toBe(false);
  });
});

describe("timer helpers", () => {
  it("count down from the server deadline regardless of the device clock", () => {
    const deadline = "2026-11-19T10:30:00Z";
    const deviceNow = Date.parse("2026-11-19T09:00:00Z"); // device clock 1 hour behind
    const offset = Date.parse("2026-11-19T10:00:00Z") - deviceNow;
    expect(formatClock(remainingMs(deadline, offset, deviceNow))).toBe("30:00");
    expect(formatClock(-5)).toBe("00:00");
    expect(isAnswered({ text: "  " })).toBe(false);
    expect(isAnswered({ choices: ["A"] })).toBe(true);
    expect(isAnswered(null)).toBe(false);
  });
});

// ------------------------------------------------------------------------------ pages
const TEST = {
  test_id: TID,
  code: "DEMO-1",
  title: "Synthetic Listening Test",
  description: "Synthetic description",
  difficulty: "medium",
  tags: [],
  duration_seconds: 1800,
  book_title: "Synthetic Collection",
  edition_label: "1st",
  locked: false,
  sections: 4,
  questions: 40,
  published_at: "2026-11-19T10:00:00Z",
  progress: {
    completed: 0,
    best_raw: null,
    last_completed_at: null,
    open_attempt_id: null,
    open_attempt_mode: null,
  },
};

function attempt(over: Record<string, unknown> = {}) {
  return {
    id: AID,
    test_id: TID,
    mode: "practice",
    status: "in_progress",
    test: { title: "Synthetic Listening Test", code: "DEMO-1", book_title: "Synthetic Collection" },
    started_at: "2026-11-19T10:00:00Z",
    deadline_at: null,
    submitted_at: null,
    completed_at: null,
    submitted_by: null,
    server_now: "2026-11-19T10:05:00Z",
    writer_epoch: 1,
    questions_total: 7,
    answered: 0,
    raw_score: null,
    max_score: null,
    band_estimate: null,
    rules: {
      timing: { listening_seconds: 1800, transfer_time_seconds: 120, enforce: false },
      listening: { max_plays: null, allow_seek: true },
    },
    ...over,
  };
}

describe("ListeningHome", () => {
  it("shows published tests, real progress and a continue action", async () => {
    const { container } = renderWithProviders(<ListeningHome />, {
      routes: {
        "GET /api/v1/listening/tests": () =>
          json([
            TEST,
            {
              ...TEST,
              test_id: "other",
              title: "Second test",
              progress: { ...TEST.progress, open_attempt_id: AID, open_attempt_mode: "exam" },
            },
          ]),
        "GET /api/v1/attempts": () =>
          json({
            items: [
              attempt({ status: "completed", raw_score: 30, max_score: 40 }),
              attempt({ id: "open1" }),
            ],
          }),
      },
    });
    expect(await screen.findByRole("link", { name: "Synthetic Listening Test" })).toHaveAttribute(
      "href",
      `/listening/tests/${TID}`,
    );
    expect(screen.getByText("Completed", { selector: "dt" }).nextSibling).toHaveTextContent("1");
    expect(screen.getByText("Average").nextSibling).toHaveTextContent("75%");
    expect(screen.getByText("Continue where you left off")).toBeInTheDocument();
    const second = screen.getByRole("link", { name: "Second test" }).closest("li")!;
    expect(within(second).getByRole("link", { name: /Continue/ })).toHaveAttribute(
      "href",
      `/exam/listening/${AID}`,
    );
    expect(await axeViolations(container)).toEqual([]);
  });

  it("has an honest empty state when nothing is published", async () => {
    renderWithProviders(<ListeningHome />, {
      routes: {
        "GET /api/v1/listening/tests": () => json([]),
        "GET /api/v1/attempts": () => json({ items: [] }),
      },
    });
    expect(await screen.findByText("No Listening tests published yet")).toBeInTheDocument();
  });
});

describe("TestIntro", () => {
  it("starts one server attempt per click storm (same idempotency key) and opens the exam room", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    renderWithProviders(<TestIntro testId={TID} />, {
      routes: {
        [`GET /api/v1/listening/tests/${TID}`]: () =>
          json({
            ...TEST,
            section_list: [1, 2, 3, 4].map((n) => ({
              section_no: n,
              title: `Part title ${n}`,
              context: null,
              questions: 10,
              number_from: n * 10 - 9,
              number_to: n * 10,
              question_types: ["note_completion"],
              has_audio: true,
            })),
            modes: [
              {
                mode: "practice",
                timed: false,
                time_limit_seconds: 1920,
                max_plays: null,
                allow_seek: true,
                auto_submit: false,
              },
              {
                mode: "exam",
                timed: true,
                time_limit_seconds: 1920,
                max_plays: 1,
                allow_seek: false,
                auto_submit: true,
              },
            ],
            default_mode: "practice",
            attempts: [],
          }),
        "POST /api/v1/attempts": (_i, r) => {
          keys.push(r!.headers.get("Idempotency-Key") ?? "");
          return keys.length === 1
            ? json({ code: "internal_error", title: "x" }, 503)
            : json(attempt({ status: "created" }), 201);
        },
      },
    });
    expect(await screen.findByText("The four parts")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Exam mode/ }));
    expect(screen.getByText(/plays once, without pausing or rewinding/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Start exam" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument(); // network failure shown
    await user.click(screen.getByRole("button", { name: "Start exam" })); // retry
    await waitFor(() => expect(router.push).toHaveBeenCalledWith(`/exam/listening/${AID}`));
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]); // the retry cannot create a second attempt
  });
});

const CONTENT = {
  version_id: "v1",
  duration_seconds: 1800,
  sections: [1, 2, 3, 4].map((n) => ({
    section_no: n,
    title: `Synthetic part ${n}`,
    context: null,
    instructions: null,
    has_audio: true,
    groups:
      n === 1 ? [GROUPS.form_completion!, GROUPS.mcq_single!] : n === 2 ? [GROUPS.mcq_multi!] : [],
  })),
};

function roomRoutes(over: Record<string, Handler> = {}): Record<string, Handler> {
  return {
    [`GET /api/v1/attempts/${AID}`]: () => json(attempt()),
    [`GET /api/v1/attempts/${AID}/content`]: () => json(CONTENT),
    [`GET /api/v1/attempts/${AID}/answers`]: () =>
      json({
        answers: [
          {
            question_id: "q2",
            response: { choice: "C" },
            writer_epoch: 1,
            client_revision: 4,
            flagged: false,
            saved_at: "x",
          },
        ],
        server_now: "2026-11-19T10:05:00Z",
      }),
    [`PUT /api/v1/attempts/${AID}/answers`]: async (_i, r) => {
      const body = (await r!.clone().json()) as {
        answers: { question_id: string; client_revision: number; response: unknown }[];
      };
      return json({
        stored: body.answers.map((a) => ({ ...a, writer_epoch: 1, flagged: false, saved_at: "x" })),
        server_now: "2026-11-19T10:05:01Z",
        deadline_at: null,
      });
    },
    ...over,
  };
}

describe("ExamRoom", () => {
  it("recovers server answers plus unsaved local ones after a refresh", async () => {
    rememberLease(AID, 1, "tok-0123456789");
    const local = new AnswerQueue(
      AID,
      { epoch: 1, token: "tok-0123456789" },
      { onState: () => {}, onServerTime: () => {}, onFatal: () => {} },
    );
    local.set("q1", { text: "typed before refresh" });
    local.stop();
    const { container } = renderWithProviders(<ExamRoom attemptId={AID} />, {
      routes: roomRoutes(),
    });
    expect(await screen.findByRole("textbox", { name: "Question 1" })).toHaveValue(
      "typed before refresh",
    );
    expect(screen.getByRole("radio", { name: /C Synthetic C/ })).toBeChecked(); // from the server
    expect(
      screen.getByRole("button", { name: "Question 2, part 1, answered" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Question 4–5, part 2, not answered" }),
    ).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("navigates parts and questions, and confirms before submitting", async () => {
    const user = userEvent.setup();
    rememberLease(AID, 1, "tok-0123456789");
    let submitted: unknown = null;
    renderWithProviders(<ExamRoom attemptId={AID} />, {
      routes: roomRoutes({
        [`POST /api/v1/attempts/${AID}/submit`]: async (_i, r) => {
          submitted = {
            key: r!.headers.get("Idempotency-Key"),
            token: r!.headers.get("X-Writer-Token"),
            body: await r!.clone().json(),
          };
          return json(attempt({ status: "completed" }));
        },
      }),
    });
    await screen.findByRole("textbox", { name: "Question 1" });
    await user.click(
      within(screen.getByRole("navigation", { name: "Test parts" })).getByRole("button", {
        name: /^Part 2/,
      }),
    );
    expect(
      screen.getByRole("heading", { level: 1, name: "Part 2: Synthetic part 2" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Review & submit/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/1 of 4 questions answered, 3 unanswered/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(`/listening/attempts/${AID}`));
    expect(submitted).toMatchObject({ token: "tok-0123456789", body: { writer_epoch: 1 } });
    expect(storedLease(AID)).toBeNull(); // local journal cleared after submission
  });

  it("asks before taking over an attempt that another browser is writing", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ExamRoom attemptId={AID} />, {
      routes: roomRoutes({
        [`POST /api/v1/attempts/${AID}/resume`]: () =>
          json({
            attempt: attempt({ writer_epoch: 2 }),
            writer_epoch: 2,
            writer_token: "tok-new-0123456789",
          }),
      }),
    });
    expect(await screen.findByText("Continue this test here?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue on this device" }));
    expect(await screen.findByRole("textbox", { name: "Question 1" })).toBeInTheDocument();
    expect(storedLease(AID)).toEqual({ epoch: 2, token: "tok-new-0123456789" });
  });

  it("shows the server-synced countdown in exam mode", async () => {
    rememberLease(AID, 1, "tok-0123456789");
    renderWithProviders(<ExamRoom attemptId={AID} />, {
      routes: roomRoutes({
        [`GET /api/v1/attempts/${AID}`]: () =>
          json(
            attempt({
              mode: "exam",
              deadline_at: "2026-11-19T10:32:00Z",
              server_now: "2026-11-19T10:05:00Z",
              rules: {
                timing: { listening_seconds: 1800, transfer_time_seconds: 120, enforce: true },
                listening: { max_plays: 1, allow_seek: false },
              },
            }),
          ),
      }),
    });
    await screen.findByRole("textbox", { name: "Question 1" });
    const clock = screen.getByText("Time left", { exact: false }).parentElement!;
    expect(["Time left 27:00", "Time left 26:59", "Time left 26:58"]).toContain(clock.textContent);
  });
});

describe("AudioPlayer", () => {
  it("requests the signed URL only when played; exam mode disables seeking", async () => {
    const user = userEvent.setup();
    const { fetchMock } = renderWithProviders(
      <AudioPlayer attemptId={AID} sectionNo={1} exam hasAudio />,
      {
        routes: {
          [`POST /api/v1/attempts/${AID}/sections/1/audio-url`]: () =>
            json({
              url: "http://localhost:9000/x.wav",
              expires_in_seconds: 2820,
              offset_ms: 0,
              allow_seek: false,
              max_plays: 1,
              plays_used: 1,
            }),
        },
      },
    );
    expect(screen.getByText(/plays once and cannot be paused or rewound/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([r]) => r instanceof Request && r.url.includes("audio-url")),
    ).toBe(false);
    expect(screen.getByRole("slider", { name: "Recording position" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Start recording" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([r]) => r instanceof Request && r.url.includes("audio-url")),
      ).toBe(true),
    );
  });

  it("says so when a part has no recording", () => {
    renderWithProviders(
      <AudioPlayer attemptId={AID} sectionNo={1} exam={false} hasAudio={false} />,
    );
    expect(screen.getByText("This part has no recording.")).toBeInTheDocument();
  });
});

describe("AttemptResult", () => {
  it("shows the server score, an honest band notice and the answer review", async () => {
    const user = userEvent.setup();
    const completed = attempt({
      status: "completed",
      completed_at: "2026-11-19T10:30:00Z",
      submitted_by: "candidate",
      raw_score: 1,
      max_score: 4,
    });
    renderWithProviders(<AttemptResult attemptId={AID} />, {
      routes: {
        [`GET /api/v1/attempts/${AID}`]: () => json(completed),
        [`GET /api/v1/attempts/${AID}/result`]: () =>
          json({
            attempt: completed,
            raw_score: 1,
            max_score: 4,
            percentage: 25,
            correct: 1,
            incorrect: 1,
            unanswered: 1,
            band_estimate: null,
            band_available: false,
            sections: [
              { section_no: 1, marks: 1, max: 2, correct: 1, questions: 2, unanswered: 0 },
              { section_no: 2, marks: 0, max: 2, correct: 0, questions: 1, unanswered: 1 },
            ],
            question_types: [
              {
                question_type: "form_completion",
                marks: 1,
                max: 1,
                correct: 1,
                questions: 1,
                unanswered: 0,
              },
            ],
          }),
        [`GET /api/v1/attempts/${AID}/review`]: () =>
          json({
            attempt: completed,
            content: CONTENT,
            items: [
              {
                question_id: "q1",
                section_no: 1,
                question_type: "form_completion",
                number_from: 1,
                number_to: 1,
                marks: 1,
                marks_awarded: 1,
                is_correct: true,
                reason: "correct",
                response: { text: "library" },
                accepted: [["the library", "library"]],
                explanation: textToDoc("Synthetic explanation."),
              },
              {
                question_id: "q2",
                section_no: 1,
                question_type: "mcq_single",
                number_from: 2,
                number_to: 2,
                marks: 1,
                marks_awarded: 0,
                is_correct: false,
                reason: "incorrect",
                response: { choice: "A" },
                accepted: [["B"]],
                explanation: null,
              },
              {
                question_id: "q4",
                section_no: 2,
                question_type: "mcq_multi",
                number_from: 4,
                number_to: 5,
                marks: 2,
                marks_awarded: 0,
                is_correct: false,
                reason: "no_response",
                response: null,
                accepted: [["A"], ["D"]],
                explanation: null,
              },
            ],
          }),
      },
    });
    expect(await screen.findByText("Answer review")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(
      screen.getByText("Not available yet: no approved score-to-band table."),
    ).toBeInTheDocument();
    expect(screen.getByText("the library / library")).toBeInTheDocument();
    expect(screen.getByText("B (Synthetic B)")).toBeInTheDocument(); // option labels explained
    expect(screen.getByText("Not answered", { selector: "span" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mistakes only" }));
    expect(screen.queryByText("the library / library")).not.toBeInTheDocument();
  });

  it("never shows answers for an attempt that is still running", async () => {
    renderWithProviders(<AttemptResult attemptId={AID} />, {
      routes: { [`GET /api/v1/attempts/${AID}`]: () => json(attempt()) },
    });
    expect(await screen.findByText("This attempt has not been submitted")).toBeInTheDocument();
  });
});
