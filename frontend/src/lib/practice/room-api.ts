/**
 * AI Speaking Room API (/api/v1/speaking/examiners|room-tests|rooms). The room is a Speaking
 * session: answers are uploaded with the existing verified recording flow (`uploadRecording`).
 */

import { browserApi } from "@/lib/api/client";
import { unwrap } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type Examiner = S["ExaminerOut"];
export type RoomTest = S["RoomTestOut"];
export type Room = S["RoomOut"];
export type RoomTurn = S["TurnOut"];
export type RoomSummary = S["RoomSummaryOut"];
export type RoomStep = S["CurrentStepOut"];

export async function fetchExaminers(): Promise<Examiner[]> {
  return unwrap(await browserApi.GET("/api/v1/speaking/examiners", { cache: "no-store" }));
}

export async function fetchRoomTests(): Promise<RoomTest[]> {
  return unwrap(await browserApi.GET("/api/v1/speaking/room-tests", { cache: "no-store" }));
}

export async function fetchRooms(): Promise<RoomSummary[]> {
  return unwrap(await browserApi.GET("/api/v1/speaking/rooms", { cache: "no-store" }));
}

export async function createRoom(examinerId: string, configId: string): Promise<Room> {
  return unwrap(
    await browserApi.POST("/api/v1/speaking/rooms", {
      body: {
        examiner_id: examinerId,
        config_id: configId,
        voice_processing_consent: true,
        audio_recording_consent: true,
      },
    }),
  );
}

const path = (id: string) => ({ params: { path: { room_id: id } } });

export async function fetchRoom(id: string): Promise<Room> {
  return unwrap(
    await browserApi.GET("/api/v1/speaking/rooms/{room_id}", { cache: "no-store", ...path(id) }),
  );
}

export async function enterRoom(id: string): Promise<S["EnterOut"]> {
  return unwrap(await browserApi.POST("/api/v1/speaking/rooms/{room_id}/enter", path(id)));
}

export async function advanceRoom(id: string, step: number): Promise<Room> {
  return unwrap(
    await browserApi.POST("/api/v1/speaking/rooms/{room_id}/advance", {
      ...path(id),
      body: { step },
    }),
  );
}

export async function endRoom(id: string): Promise<Room> {
  return unwrap(await browserApi.POST("/api/v1/speaking/rooms/{room_id}/end", path(id)));
}

export function clockOf(ms: number | null | undefined): string {
  const total = Math.max(0, Math.floor((ms ?? 0) / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

export const TONE: Record<string, string> = {
  primary: "from-primary/90 to-primary/60 text-primary-foreground",
  success: "from-success/90 to-success/60 text-white",
  warning: "from-warning/90 to-warning/60 text-white",
  info: "from-info/90 to-info/60 text-white",
};

export const DIFFICULTY: Record<string, string> = {
  supportive: "Supportive",
  standard: "Standard",
  challenging: "Challenging",
};

export async function fetchVoiceToken(id: string): Promise<S["VoiceConnectionOut"]> {
  return unwrap(await browserApi.POST("/api/v1/speaking/rooms/{room_id}/voice-token", path(id)));
}
