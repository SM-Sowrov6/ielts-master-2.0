import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExaminerConfigEditor } from "@/components/admin/examiner/examiner-admin";
import type { Me } from "@/lib/auth/api";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const CID = "00000000-0000-7000-8000-0000000000f1";
const OWNER: Me = {
  id: "00000000-0000-7000-8000-000000000001",
  email: "owner@example.test",
  full_name: "Owner",
  email_verified: true,
  roles: ["super_admin"],
  permissions: ["admin.access", "content.edit", "content.publish"],
};

function json(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });
}

const body = {
  title: "Synthetic — AI examiner",
  part1_questions: [0],
  part2_rounding: [],
  part3_questions: [],
  timing: {
    part1_answer_seconds: 45,
    part2_prep_seconds: 60,
    part2_speak_seconds: 120,
    part3_answer_seconds: 75,
    max_total_minutes: 15,
  },
  follow_ups: { enabled: true, max_per_question: 1, use_candidate_answers: true },
  instructions: {
    role: "r",
    introduction: "Hello, I am {examiner}.",
    tone: "t",
    question_delivery: "q",
    follow_up_rules: "f",
    irrelevant_answers: "i",
    silence: "s",
    to_part2: "Now Part 2.",
    to_part3: "Now Part 3.",
    completion: "Thank you.",
    confidentiality: "c",
  },
  difficulty: "standard",
  criteria: ["FC", "LR", "GRA", "PR"],
};

describe("ExaminerConfigEditor", () => {
  it("previews the examiner flow and blocks publishing while issues remain", async () => {
    renderWithProviders(<ExaminerConfigEditor configId={CID} user={OWNER} />, {
      routes: {
        [`GET /api/v1/admin/speaking/configs/${CID}`]: () =>
          json({
            id: CID,
            test_id: "t",
            test_version_id: "v",
            test_title: "Synthetic Speaking",
            title: body.title,
            status: "draft",
            revision: "2026-11-19T10:00:00Z",
            published_at: null,
            body,
            issues: ["Part 3 needs at least one question."],
          }),
        [`GET /api/v1/admin/speaking/configs/${CID}/preview`]: () =>
          json({
            issues: ["Part 3 needs at least one question."],
            rules: ["Ask one question at a time."],
            plan: [
              {
                step: 0,
                role: "examiner",
                part_no: 1,
                kind: "intro",
                text: "Hello, I am your examiner.",
              },
              {
                step: 1,
                role: "examiner",
                part_no: 1,
                kind: "question",
                text: "Where is your hometown?",
              },
              {
                step: 2,
                role: "candidate",
                part_no: 1,
                kind: "answer",
                text: "Where is your hometown?",
                answer_seconds: 45,
                prep_seconds: 0,
              },
            ],
            available: {
              part1: ["Where is your hometown?", "Do you like it?"],
              part2_rounding: [],
              part3: ["Why do people move?"],
              cue_card: { prompt: "Describe an object", points: ["what it is"] },
            },
          }),
      },
    });
    expect(await screen.findByText("Hello, I am your examiner.")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Part 3 needs at least one question.");
    expect(screen.getByRole("button", { name: "Publish" })).toBeDisabled();
    expect(screen.getByText("Describe an object")).toBeInTheDocument();
    expect(screen.getByLabelText("Introduction message")).toHaveValue("Hello, I am {examiner}.");
    expect(screen.getByRole("button", { name: /Why do people move/ })).toBeInTheDocument();
  });
});
