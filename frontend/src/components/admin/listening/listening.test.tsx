import { focusManager } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  cloneGroup,
  draftFromDocument,
  joinAlternatives,
  newGroup,
  nextNumber,
  saveBody,
  splitAlternatives,
  swapNumbers,
  textAnswer,
  usesOptions,
} from "@/components/admin/listening/editor/model";
import { ListeningEditor } from "@/components/admin/listening/editor/listening-editor";
import { ListeningDashboard } from "@/components/admin/listening/listening-dashboard";
import { ListeningPreview } from "@/components/admin/listening/listening-preview";
import { issueTarget, issuesFor, requestErrorsToIssues } from "@/lib/admin/issues";
import type { EditorDocument, QuestionDoc, SectionDoc } from "@/lib/admin/listening-api";
import { docToText, textToDoc } from "@/lib/admin/richtext";
import { UploadError, uploadMedia } from "@/lib/admin/upload";
import type { Me } from "@/lib/auth/api";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/listening",
  useRouter: () => router,
}));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });

const OWNER: Me = {
  id: "00000000-0000-7000-8000-0000000000a1",
  email: "owner@example.test",
  full_name: "Synthetic Owner",
  email_verified: true,
  roles: ["super_admin"],
  permissions: [
    "admin.access",
    "content.edit",
    "content.review",
    "content.publish",
    "media.upload",
  ],
};
const REVIEWER: Me = {
  ...OWNER,
  id: "00000000-0000-7000-8000-0000000000b2",
  full_name: "Synthetic Reviewer",
  roles: ["reviewer"],
  permissions: ["admin.access", "content.review"],
};

const VID = "00000000-0000-7000-8000-00000000c001";
const TID = "00000000-0000-7000-8000-00000000d001";

function doc(
  over: Partial<EditorDocument["version"]> = {},
  sections?: SectionDoc[],
): EditorDocument {
  return {
    module: "listening",
    variant: "common",
    writing_tasks: [],
    speaking_parts: [],
    test: {
      id: TID,
      code: "L-001",
      title: "Synthetic Listening",
      admin_notes: "staff only",
      live_version_id: null,
    },
    catalog: {
      book_id: "b",
      book_title: "Synthetic Collection",
      edition_id: "e",
      edition_label: "1st",
      license_id: "l",
    },
    version: {
      id: VID,
      version_no: 1,
      status: "draft",
      approved: false,
      revision: "2026-11-19T10:00:00Z",
      created_by: OWNER.id,
      created_by_name: OWNER.full_name,
      change_note: null,
      description: null,
      difficulty: "medium",
      tags: ["synthetic"],
      submitted_at: null,
      published_at: null,
      reviews: [],
      ...over,
    },
    duration_seconds: 1800,
    sections:
      sections ??
      [1, 2, 3, 4].map((n) => ({ section_no: n, title: null, groups: [], passages: [] })),
    assets: [],
    versions: [
      {
        id: VID,
        version_no: 1,
        status: over.status ?? "draft",
        updated_at: "2026-11-19T10:00:00Z",
      },
    ],
  };
}

const QUESTION_TYPES = [
  "mcq_single",
  "mcq_multi",
  "matching_features",
  "sentence_completion",
  "summary_completion",
  "note_completion",
  "table_completion",
  "flowchart_completion",
  "form_completion",
  "diagram_labelling",
  "map_labelling",
  "plan_labelling",
  "short_answer",
].map((code) => ({ code, family: "text", modules: ["listening"] }));

beforeEach(() => {
  vi.clearAllMocks();
  document.documentElement.lang = "en";
  document.title = "Listening Management · IELTS MASTER 2.0";
});

// ------------------------------------------------------------------------------ model
describe("editor model", () => {
  it("round-trips the server document into a save body with the loaded revision", () => {
    const d = doc();
    const draft = draftFromDocument(d);
    expect(draft.minutes).toBe("30");
    expect(draft.tags).toBe("synthetic");
    const body = saveBody(d, { ...draft, tags: "a, b, a", minutes: "35", title: " New " });
    expect(body.revision).toBe(d.version.revision);
    expect(body.tags).toEqual(["a", "b"]);
    expect(body.duration_seconds).toBe(2100);
    expect(body.title).toBe("New");
    expect(body.sections).toHaveLength(4);
  });

  it("authors accepted alternatives in the existing key notation", () => {
    expect(joinAlternatives(["car park", " parking lot ", ""])).toBe("car park / parking lot");
    expect(splitAlternatives("car park / parking lot")).toEqual(["car park", "parking lot"]);
    expect(splitAlternatives("colour/color")).toEqual(["colour/color"]); // word-level stays
    expect(textAnswer(["(the) library"], "text")).toEqual([
      { value: "(the) library", slot: 1, match_mode: "text" },
    ]);
    expect(textAnswer(["  "], "numeric")).toEqual([]);
  });

  it("numbers questions across the test and keeps spans when reordering", () => {
    const sections: SectionDoc[] = [
      { section_no: 1, groups: [newGroup("form_completion", 1)], passages: [] },
      { section_no: 2, groups: [newGroup("mcq_multi", 2)], passages: [] },
    ];
    expect(nextNumber(sections)).toBe(4); // mcq_multi covers 2-3
    const qs: QuestionDoc[] = [
      { number_from: 5, number_to: 6, answers: [] },
      { number_from: 7, answers: [] },
    ];
    const swapped = swapNumbers(qs, 0, 1);
    expect(swapped.map((q) => [q.number_from, q.number_to ?? null])).toEqual([
      [5, null],
      [6, 7],
    ]);
    const copy = cloneGroup(
      {
        ...newGroup("note_completion", 1),
        questions: [{ lineage_id: "keep?", number_from: 1, answers: [] }],
      },
      9,
    );
    expect(copy.questions[0]?.lineage_id).toBeUndefined(); // duplicates get a new history
    expect(copy.questions[0]?.number_from).toBe(9);
  });

  it("knows which canonical types answer with options", () => {
    expect(usesOptions(newGroup("mcq_single", 1))).toBe(true);
    expect(usesOptions(newGroup("note_completion", 1))).toBe(false);
    expect(
      usesOptions({ ...newGroup("summary_completion", 1), config: { answer_format: "option" } }),
    ).toBe(true);
  });

  it("maps validator locations onto sections, groups and questions", () => {
    expect(issueTarget("listening/common > section 2 > group 3 (mcq_single) > Q14")).toEqual({
      section: 2,
      group: 2,
      question: 14,
    });
    const issues = [
      {
        severity: "error" as const,
        code: "a",
        location: "listening/common > section 1",
        message: "s",
      },
      {
        severity: "error" as const,
        code: "b",
        location: "listening/common > section 1 > group 1 (x) > Q3",
        message: "q",
      },
    ];
    expect(issuesFor(issues, { section: 1 }).map((i) => i.code)).toEqual(["a"]);
    expect(issuesFor(issues, { section: 1, group: 0, question: 3 }).map((i) => i.code)).toEqual([
      "b",
    ]);
  });

  it("places request-schema errors on the exact question in plain language", () => {
    const sections: SectionDoc[] = [
      { section_no: 1, groups: [newGroup("mcq_single", 7)], passages: [] },
    ];
    const issues = requestErrorsToIssues(
      [
        {
          loc: ["body", "sections", 0, "groups", 0, "questions", 0, "answers"],
          msg: "List should have at least 1 item",
          code: "too_short",
        },
        {
          loc: ["body", "sections", 0, "groups", 0, "options", 1, "text"],
          msg: "String should have at least 1 character",
          code: "string_too_short",
        },
        { loc: ["body", "title"], msg: "x", code: "string_too_short" },
      ],
      sections,
    );
    expect(issues.map((i) => [i.location, i.message])).toEqual([
      ["listening/common > section 1 > group 1 (mcq_single) > Q7", "Add the correct answer."],
      ["listening/common > section 1 > group 1 (mcq_single)", "Every option needs text."],
      ["test", "Enter a title (at most 300 characters)."],
    ]);
    expect(issuesFor(issues, { section: 1, group: 0, question: 7 })).toHaveLength(1);
  });

  it("stores plain text as allow-listed rich text only", () => {
    const d = textToDoc("Line one\nLine two");
    expect(d).toEqual({
      type: "doc",
      content: [
        { type: "paragraph", content: [{ type: "text", text: "Line one" }] },
        { type: "paragraph", content: [{ type: "text", text: "Line two" }] },
      ],
    });
    expect(docToText(d)).toBe("Line one\nLine two");
    expect(textToDoc("   ")).toBeNull();
    expect(docToText("<b>html</b>")).toBe("");
  });
});

// ------------------------------------------------------------------------------ upload
class FakeXhr {
  static last: FakeXhr | null = null;
  static status = 200;
  upload: {
    onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null;
  } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 0;
  url = "";
  headers: Record<string, string> = {};
  open(_m: string, url: string) {
    this.url = url;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send() {
    FakeXhr.last = this;
    this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
    this.status = FakeXhr.status;
    this.onload?.();
  }
}

describe("uploadMedia", () => {
  it("hashes, uploads with progress to the presigned URL and returns only the verified asset", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    FakeXhr.status = 200;
    const asset = {
      id: "a1",
      kind: "audio",
      status: "ready",
      mime_type: "audio/wav",
      size_bytes: 4,
      original_filename: "x.wav",
    };
    const { fetchMock } = renderWithProviders(<div />, {
      routes: {
        "POST /api/v1/admin/content/media": () =>
          json(
            {
              asset: { ...asset, status: "uploading" },
              upload_url: "http://localhost:9000/put",
              method: "PUT",
              headers: { "Content-Type": "audio/wav" },
              expires_in_seconds: 300,
            },
            201,
          ),
        "POST /api/v1/admin/content/media/a1/complete": () => json(asset),
      },
    });
    const phases: string[] = [];
    const progress: number[] = [];
    const file = new File([new Uint8Array([82, 73, 70, 70])], "x.wav", { type: "audio/wav" });
    const result = await uploadMedia(file, {
      testId: TID,
      kind: "audio",
      onPhase: (p) => phases.push(p),
      onProgress: (f) => progress.push(f),
    });
    expect(result.status).toBe("ready");
    expect(phases).toEqual(["hashing", "uploading", "verifying"]);
    expect(progress).toEqual([0.5]);
    expect(FakeXhr.last?.url).toBe("http://localhost:9000/put");
    expect(FakeXhr.last?.headers["Content-Type"]).toBe("audio/wav");
    const start = fetchMock.mock.calls.find(
      ([r]) => r instanceof Request && r.url.endsWith("/media"),
    )?.[0] as Request;
    const body = (await start.clone().json()) as { sha256: string; size_bytes: number };
    expect(body.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(body.size_bytes).toBe(4);
  });

  it("refuses unsupported files and reports storage or verification failures", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    await expect(
      uploadMedia(new File(["x"], "x.txt", { type: "text/plain" }), {
        testId: TID,
        kind: "audio",
        onPhase: () => {},
        onProgress: () => {},
      }),
    ).rejects.toBeInstanceOf(UploadError);
    renderWithProviders(<div />, {
      routes: {
        "POST /api/v1/admin/content/media": () =>
          json(
            {
              asset: {
                id: "a2",
                kind: "audio",
                status: "uploading",
                mime_type: "audio/mpeg",
                size_bytes: 1,
                original_filename: "x.mp3",
              },
              upload_url: "http://s/put",
              method: "PUT",
              headers: {},
              expires_in_seconds: 300,
            },
            201,
          ),
        "POST /api/v1/admin/content/media/a2/complete": () =>
          json(
            {
              code: "media_rejected",
              title: "The file was rejected",
              detail: "The file's content does not match its declared type.",
            },
            422,
          ),
      },
    });
    FakeXhr.status = 200;
    await expect(
      uploadMedia(new File(["x"], "x.mp3", { type: "audio/mpeg" }), {
        testId: TID,
        kind: "audio",
        onPhase: () => {},
        onProgress: () => {},
      }),
    ).rejects.toMatchObject({ code: "media_rejected" });
    FakeXhr.status = 403;
    await expect(
      uploadMedia(new File(["x"], "x.mp3", { type: "audio/mpeg" }), {
        testId: TID,
        kind: "audio",
        onPhase: () => {},
        onProgress: () => {},
      }),
    ).rejects.toThrow("Storage rejected the upload (HTTP 403).");
  });
});

// ------------------------------------------------------------------------------ dashboard
const ROW = {
  test_id: TID,
  version_id: VID,
  version_no: 1,
  code: "L-001",
  title: "Synthetic Listening",
  book_title: "Synthetic Collection",
  edition_label: "1st",
  status: "approved",
  difficulty: "hard",
  sections: 4,
  questions: 40,
  duration_seconds: 1800,
  updated_at: "2026-11-19T10:00:00Z",
  created_by: OWNER.id,
  created_by_name: "Synthetic Owner",
  live_version_id: null,
};

describe("ListeningDashboard", () => {
  it("shows live statistics and rows with role-appropriate actions", async () => {
    const user = userEvent.setup();
    const { container, fetchMock } = renderWithProviders(
      <ListeningDashboard permissions={OWNER.permissions} />,
      {
        routes: {
          "GET /api/v1/admin/content/listening/overview": () =>
            json({ total: 3, draft: 1, in_review: 0, approved: 1, published: 1, archived: 0 }),
          "GET /api/v1/admin/content/listening/tests": () =>
            json({ items: [ROW], total: 1, offset: 0, limit: 10 }),
        },
      },
    );
    expect(await screen.findByRole("link", { name: "Synthetic Listening" })).toHaveAttribute(
      "href",
      `/admin/listening/${VID}`,
    );
    expect(screen.getByText("Total tests").nextSibling).toHaveTextContent("3");
    expect(within(screen.getByRole("table")).getByText("Advanced")).toBeInTheDocument();
    expect(screen.getByText("Approved", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /New Listening test/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Actions for Synthetic Listening" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Publish" })).toBeInTheDocument();
    expect(within(menu).queryByRole("menuitem", { name: "Archive" })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.type(screen.getByLabelText("Search"), "Synth");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([r]) => r instanceof Request && r.url.includes("search=Synth")),
      ).toBe(true),
    );
    expect(await axeViolations(container)).toEqual([]);
  });

  it("hides editing and publishing from a reviewer, and has honest empty and error states", async () => {
    const { unmount } = renderWithProviders(
      <ListeningDashboard permissions={REVIEWER.permissions} />,
      {
        routes: {
          "GET /api/v1/admin/content/listening/overview": () =>
            json({ total: 0, draft: 0, in_review: 0, approved: 0, published: 0, archived: 0 }),
          "GET /api/v1/admin/content/listening/tests": () =>
            json({ items: [], total: 0, offset: 0, limit: 10 }),
        },
      },
    );
    expect(await screen.findByText("No Listening tests yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /New Listening test/ })).not.toBeInTheDocument();
    unmount();
    renderWithProviders(<ListeningDashboard permissions={OWNER.permissions} />, {
      routes: {
        "GET /api/v1/admin/content/listening/overview": () =>
          json({ code: "internal_error", title: "x" }, 500),
        "GET /api/v1/admin/content/listening/tests": () =>
          json({ code: "internal_error", title: "x" }, 500),
      },
    });
    expect(await screen.findByText("Tests could not be loaded")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------ editor
type Handler = (init?: RequestInit, request?: Request) => Response | Promise<Response>;

function editorRoutes(d: EditorDocument, extra: Record<string, Handler> = {}) {
  return {
    [`GET /api/v1/admin/content/versions/${VID}`]: () => json(d),
    "GET /api/v1/admin/content/question-types": () => json(QUESTION_TYPES),
    ...extra,
  };
}

describe("ListeningEditor", () => {
  it("builds questions with the registry types and shows field-level errors from the server", async () => {
    const user = userEvent.setup();
    let saved: unknown = null;
    const { container } = renderWithProviders(<ListeningEditor versionId={VID} user={OWNER} />, {
      routes: editorRoutes(doc(), {
        [`PUT /api/v1/admin/content/versions/${VID}`]: async (
          _init?: RequestInit,
          request?: Request,
        ) => {
          saved = await request?.clone().json();
          return json(
            {
              code: "content_validation_failed",
              title: "Content failed validation",
              issues: [
                {
                  severity: "error",
                  code: "key_count",
                  location: "listening/common > section 1 > group 1 (form_completion) > Q1",
                  message: "Exactly one answer key (slot 1) is required.",
                },
              ],
            },
            422,
          );
        },
      }),
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: "Synthetic Listening" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Section 1/ }));
    expect(screen.getByRole("heading", { name: "Section 1" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add question group" }));
    expect(
      screen.getByRole("heading", { name: /Group 1: Multiple choice \(one answer\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Unsaved changes. Uploaded files are attached only when you save the draft.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(
      await screen.findByText("Exactly one answer key (slot 1) is required."),
    ).toBeInTheDocument();
    const body = saved as { revision: string; sections: SectionDoc[] };
    expect(body.revision).toBe("2026-11-19T10:00:00Z");
    expect(body.sections[0]?.groups?.[0]?.question_type).toBe("mcq_single");
    expect(
      screen.getByRole("button", { name: "Section 1, 1 error, Questions 1–1 (1)" }),
    ).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("shows incomplete questions next to the field when the request schema rejects a save", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ListeningEditor versionId={VID} user={OWNER} />, {
      routes: editorRoutes(doc(), {
        [`PUT /api/v1/admin/content/versions/${VID}`]: () =>
          json(
            {
              code: "validation_error",
              title: "Request validation failed",
              errors: [
                {
                  loc: ["body", "sections", 0, "groups", 0, "questions", 0, "answers"],
                  msg: "List should have at least 1 item after validation, not 0",
                  code: "too_short",
                },
              ],
            },
            422,
          ),
      }),
    });
    await user.click(await screen.findByRole("button", { name: /Section 1/ }));
    await user.click(screen.getByRole("button", { name: "Add question group" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(await screen.findByText("Add the correct answer.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Section 1, 1 error, Questions 1–1 (1)" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled(); // still unsaved
  });

  it("never overwrites unsaved edits with a newer server revision", async () => {
    const user = userEvent.setup();
    let current = doc();
    let sentRevision: string | undefined;
    const { fetchMock } = renderWithProviders(<ListeningEditor versionId={VID} user={OWNER} />, {
      routes: {
        ...editorRoutes(current),
        [`GET /api/v1/admin/content/versions/${VID}`]: () => json(current),
        [`PUT /api/v1/admin/content/versions/${VID}`]: async (_i?: RequestInit, r?: Request) => {
          sentRevision = ((await r?.clone().json()) as { revision: string }).revision;
          return json({ code: "content_draft_conflict", title: "Changed elsewhere" }, 409);
        },
      },
    });
    const title = await screen.findByLabelText("Test title");
    await user.clear(title);
    await user.type(title, "My unsaved title");
    // Another admin saves: a refetch delivers a newer revision.
    current = doc({ revision: "2026-11-19T12:00:00Z" });
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true); // the tab regains focus -> refetch
    });
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(2));
    expect(await screen.findByText(/Someone else changed this test/)).toBeInTheDocument();
    expect(screen.getByLabelText("Test title")).toHaveValue("My unsaved title");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(sentRevision).toBe("2026-11-19T10:00:00Z")); // the loaded one
  });

  it("locks published versions and offers a new revision instead", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ListeningEditor versionId={VID} user={OWNER} />, {
      routes: editorRoutes(doc({ status: "published", published_at: "2026-11-19T11:00:00Z" })),
    });
    expect(
      await screen.findByText(/Published and archived versions are immutable/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Validate & review/ }));
    expect(screen.getByRole("button", { name: "Create new revision" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit for review" })).not.toBeInTheDocument();
  });

  it("enforces four-eyes in the UI: the author cannot review; a reviewer can, but cannot publish", async () => {
    const user = userEvent.setup();
    const inReview = doc({ status: "in_review", submitted_at: "2026-11-19T10:30:00Z" });
    const { unmount } = renderWithProviders(<ListeningEditor versionId={VID} user={OWNER} />, {
      routes: editorRoutes(inReview),
    });
    await user.click(await screen.findByRole("button", { name: /Validate & review/ }));
    expect(
      screen.getByText(/another staff member must review it \(four-eyes rule\)/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    unmount();

    let reviewed: unknown = null;
    renderWithProviders(<ListeningEditor versionId={VID} user={REVIEWER} />, {
      routes: editorRoutes(inReview, {
        [`POST /api/v1/admin/content/versions/${VID}/review`]: async (
          _init?: RequestInit,
          request?: Request,
        ) => {
          reviewed = await request?.clone().json();
          return json(
            doc({ status: "in_review", approved: true, revision: "2026-11-19T10:40:00Z" }),
          );
        },
      }),
    });
    expect(
      await screen.findByText("Your role can view this test but not edit it."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Validate & review/ }));
    await user.type(screen.getByLabelText("Comment (optional)"), "Fine");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(reviewed).toEqual({ decision: "approved", comment: "Fine" }));
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------------------------ preview
describe("ListeningPreview", () => {
  it("looks like the candidate view and reveals answers only on request", async () => {
    const user = userEvent.setup();
    const sections = [1, 2, 3, 4].map((n) => ({
      section_no: n,
      title: `Synthetic part ${n}`,
      instructions: "Listen and answer.",
      context: null,
      audio_asset_id: null,
      groups:
        n === 1
          ? [
              {
                question_type: "note_completion",
                instructions: "Write ONE WORD ONLY.",
                answer_format: "text",
                config: {},
                options: [],
                image_asset_id: null,
                questions: [
                  { number_from: 1, number_to: 1, marks: 1, stem: textToDoc("Synthetic gap ____") },
                ],
                answers: [
                  {
                    number_from: 1,
                    number_to: 1,
                    accepted: [["the library", "library"]],
                    explanation: textToDoc("Because."),
                  },
                ],
              },
            ]
          : [],
    }));
    const { container } = renderWithProviders(<ListeningPreview versionId={VID} />, {
      routes: {
        [`GET /api/v1/admin/content/versions/${VID}/preview`]: () =>
          json({
            test_id: TID,
            version_id: VID,
            version_no: 1,
            status: "draft",
            title: "Synthetic Listening",
            code: "L-001",
            description: null,
            difficulty: "easy",
            duration_seconds: 1800,
            sections,
          }),
        [`GET /api/v1/admin/content/versions/${VID}`]: () => json(doc()),
      },
    });
    expect(
      await screen.findByText(/It is not an attempt: nothing is answered, scored or saved/),
    ).toBeInTheDocument();
    expect(screen.getByText("Synthetic gap ____")).toBeInTheDocument();
    expect(screen.queryByText(/the library/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show answers" }));
    expect(screen.getByText("the library | library")).toBeInTheDocument();
    expect(screen.getByText("No audio uploaded for this part yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Part 2" }));
    expect(screen.getByText("No questions in this part yet.")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});
