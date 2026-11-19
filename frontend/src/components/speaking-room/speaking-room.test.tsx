import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SpeakingLanding } from "@/components/speaking-room/landing";
import { SpeakingRoom } from "@/components/speaking-room/room";
import type { Examiner, Room } from "@/lib/practice/room-api";
import { axeViolations } from "@/test/axe";
import { renderWithProviders } from "@/test/render";

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(),
}));

const RID = "00000000-0000-7000-8000-0000000000c1";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json" },
  });
}

const EXAMINER: Examiner = {
  id: "00000000-0000-7000-8000-0000000000e1",
  code: "standard",
  name: "Daniel",
  title: "Standard examiner",
  personality: "Neutral and professional.",
  speaking_style: "Natural pace.",
  accent: null,
  difficulty: "standard",
  avatar_tone: "primary",
  voice_configured: false,
};

function room(over: Partial<Room> = {}): Room {
  return {
    id: RID,
    room_code: "room-abc",
    status: "created",
    test_title: "Synthetic Speaking",
    examiner: EXAMINER,
    timing: { part2_prep_seconds: 60, part2_speak_seconds: 120, max_total_minutes: 15 },
    criteria: ["FC", "LR", "GRA", "PR"],
    current_part: null,
    current_step: 0,
    total_steps: 12,
    answers_total: 5,
    answers_done: 0,
    current: null,
    cue_card: null,
    live_phase: null,
    transcript: [],
    voice: {
      mode: null,
      live_available: false,
      message: "Guided mode: the AI voice examiner is not connected yet.",
    },
    created_at: "2026-11-19T10:00:00Z",
    started_at: null,
    ended_at: null,
    duration_seconds: null,
    completion_reason: null,
    evaluation: null,
    model_answers: [],
    ...over,
  };
}

describe("Speaking landing", () => {
  it("presents the AI examiners and an honest empty history", async () => {
    const { container } = renderWithProviders(<SpeakingLanding />, {
      routes: {
        "GET /api/v1/speaking/examiners": () => json([EXAMINER]),
        "GET /api/v1/speaking/rooms": () => json([]),
        "GET /api/v1/speaking/room-tests": () => json([]),
        "GET /api/v1/speaking/tests": () => json([]),
      },
    });
    expect(screen.getByRole("link", { name: /Start Speaking Practice/ })).toHaveAttribute(
      "href",
      "/speaking/start",
    );
    expect(await screen.findByRole("heading", { name: "Daniel", level: 3 })).toBeInTheDocument();
    expect(screen.getByText(/voice not connected yet/)).toBeInTheDocument();
    expect(await screen.findByText("No sessions yet")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("Speaking room", () => {
  it("only lets the candidate enter after a successful microphone check", async () => {
    const track = { stop: vi.fn(), label: "Test microphone", enabled: true };
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [track],
      getAudioTracks: () => [track],
    }));
    vi.stubGlobal(
      "MediaRecorder",
      Object.assign(function MediaRecorder() {}, { isTypeSupported: () => true }),
    );
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia },
      configurable: true,
    });
    renderWithProviders(<SpeakingRoom roomId={RID} />, {
      routes: { [`GET /api/v1/speaking/rooms/${RID}`]: () => json(room()) },
    });
    const enter = await screen.findByRole("button", { name: "Enter Speaking Room" });
    expect(enter).toBeDisabled();
    expect(getUserMedia).not.toHaveBeenCalled(); // never before the candidate asks
    await userEvent.click(screen.getByRole("button", { name: /Start microphone check/ }));
    await waitFor(() => expect(enter).toBeEnabled());
    expect(screen.getByText("Device: Test microphone")).toBeInTheDocument();
  });

  it("explains a blocked microphone", async () => {
    vi.stubGlobal(
      "MediaRecorder",
      Object.assign(function MediaRecorder() {}, { isTypeSupported: () => true }),
    );
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: vi.fn(async () => Promise.reject(new Error("denied"))) },
      configurable: true,
    });
    renderWithProviders(<SpeakingRoom roomId={RID} />, {
      routes: { [`GET /api/v1/speaking/rooms/${RID}`]: () => json(room()) },
    });
    await userEvent.click(await screen.findByRole("button", { name: /Start microphone check/ }));
    expect(await screen.findByText("Microphone access was blocked")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enter Speaking Room" })).toBeDisabled();
  });

  it("shows the transcript and Evaluation Pending without inventing a score", async () => {
    renderWithProviders(<SpeakingRoom roomId={RID} />, {
      routes: {
        [`GET /api/v1/speaking/rooms/${RID}`]: () =>
          json(
            room({
              status: "completed",
              duration_seconds: 300,
              answers_done: 1,
              completion_reason: "finished",
              transcript: [
                {
                  seq: 1,
                  speaker: "examiner",
                  part_no: 1,
                  kind: "intro",
                  text: "Hello, I am Daniel.",
                  offset_ms: 0,
                  created_at: "2026-11-19T10:00:00Z",
                  recording_id: null,
                  duration_ms: null,
                  transcript_status: null,
                },
                {
                  seq: 2,
                  speaker: "candidate",
                  part_no: 1,
                  kind: null,
                  text: "",
                  offset_ms: 9000,
                  created_at: "2026-11-19T10:00:09Z",
                  recording_id: "00000000-0000-7000-8000-0000000000d1",
                  duration_ms: 42000,
                  transcript_status: "pending",
                },
              ],
              evaluation: {
                id: "e1",
                status: "unavailable",
                message:
                  "AI evaluation is not available yet: no speech-to-text or AI provider is configured.",
                band_overall: null,
                criteria: [],
                feedback: [],
                summary: null,
                off_topic: false,
                improvement_plan: [],
                not_assessed: [],
                provider: null,
                model: null,
                prompt_version: null,
                retryable: true,
                created_at: "2026-11-19T10:05:00Z",
                finished_at: "2026-11-19T10:05:01Z",
              },
            }),
          ),
      },
    });
    expect(await screen.findByRole("heading", { name: "Session complete" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evaluation Pending" })).toBeInTheDocument();
    expect(screen.getByText("Hello, I am Daniel.")).toBeInTheDocument();
    expect(screen.getByText(/written transcript appears after evaluation/)).toBeInTheDocument();
    expect(screen.queryByText(/Overall band/)).not.toBeInTheDocument();
  });
});
