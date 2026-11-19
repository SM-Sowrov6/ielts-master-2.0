"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2Icon,
  CircleAlertIcon,
  EyeIcon,
  EyeOffIcon,
  LoaderCircleIcon,
  MicIcon,
  MicOffIcon,
  PhoneOffIcon,
  RotateCcwIcon,
  SquareIcon,
  WifiIcon,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Room as LiveKitRoom, RoomEvent, Track } from "livekit-client";
import { toast } from "sonner";

import { EvaluationView, ModelAnswers } from "@/components/practice/evaluation-view";
import { Playback } from "@/components/practice/speaking";
import { ExaminerAvatar } from "@/components/speaking-room/shared";
import { ErrorState, LoadingState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { messageFor } from "@/lib/auth/api";
import { isPending, retrySpeakingEvaluation, uploadRecording } from "@/lib/practice/api";
import {
  DIFFICULTY,
  advanceRoom,
  clockOf,
  endRoom,
  enterRoom,
  fetchRoom,
  fetchVoiceToken,
  type Room,
  type RoomTurn,
} from "@/lib/practice/room-api";
import { cn } from "@/lib/utils";

const KEY = (id: string) => ["speaking", "room", id];

function preferredMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/** Microphone level 0..1 from an analyser on the given stream (no audio leaves the browser). */
function useLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    if (!stream || typeof AudioContext === "undefined") return;
    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;
    let last = 0;
    const tick = (t: number) => {
      analyser.getByteTimeDomainData(data);
      let peak = 0;
      for (const v of data) peak = Math.max(peak, Math.abs(v - 128) / 128);
      if (t - last > 80) {
        setLevel(peak);
        last = t;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      void ctx.close();
    };
  }, [stream]);
  return level;
}

function Waveform({ level, active, label }: { level: number; active: boolean; label: string }) {
  const bars = [0.5, 0.8, 1, 0.8, 0.5, 0.7, 0.9];
  return (
    <div className="flex h-10 items-center gap-1" role="img" aria-label={label}>
      {bars.map((b, i) => (
        <span
          key={i}
          className={cn(
            "w-1.5 rounded-full transition-[height] duration-100",
            active ? "bg-primary" : "bg-muted-foreground/30",
          )}
          style={{ height: `${Math.max(12, Math.min(100, (active ? level * 220 : 0) * b + 12))}%` }}
        />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------------------ waiting room
function WaitingRoom({ room, onEntered }: { room: Room; onEntered: (r: Room) => void }) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [state, setState] = useState<"idle" | "checking" | "ok" | "denied" | "unsupported">(
    typeof navigator !== "undefined" && navigator.mediaDevices && preferredMime()
      ? "idle"
      : "unsupported",
  );
  const [device, setDevice] = useState<string | null>(null);
  const level = useLevel(stream);
  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream]);
  const enter = useMutation({
    mutationFn: () => enterRoom(room.id),
    onSuccess: (out) => {
      stream?.getTracks().forEach((t) => t.stop());
      onEntered(out.room);
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  async function check() {
    setState("checking");
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      setStream(s);
      setDevice(s.getAudioTracks()[0]?.label || "Default microphone");
      setState("ok");
    } catch {
      setState("denied");
    }
  }
  const e = room.examiner;
  return (
    <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[1.1fr_1fr]">
      <section className="flex flex-col items-center gap-4 rounded-3xl border bg-gradient-to-br from-primary/10 via-card to-card p-8 text-center shadow-elevation-1">
        <ExaminerAvatar examiner={e} size="xl" />
        <div>
          <h1 className="font-heading text-2xl font-semibold">{e.name} is ready for you</h1>
          <p className="text-sm text-muted-foreground">
            {e.title} · {DIFFICULTY[e.difficulty]} · {room.test_title}
          </p>
        </div>
        <p className="max-w-md text-sm">{e.personality}</p>
        <ul className="grid w-full max-w-md gap-2 text-left text-sm">
          <li className="rounded-lg bg-background/70 p-3">
            <strong>Part 1</strong> · introduction and questions about familiar topics
          </li>
          <li className="rounded-lg bg-background/70 p-3">
            <strong>Part 2</strong> · a cue card: {room.timing.part2_prep_seconds ?? 60}s to
            prepare, up to {Math.round((room.timing.part2_speak_seconds ?? 120) / 60)} min to speak
          </li>
          <li className="rounded-lg bg-background/70 p-3">
            <strong>Part 3</strong> · a discussion of broader questions
          </li>
        </ul>
        <p className="text-xs text-muted-foreground">Room {room.room_code}</p>
      </section>
      <section aria-labelledby="mic-h" className="space-y-5 rounded-3xl border bg-card p-6">
        <h2 id="mic-h" className="font-heading text-xl font-semibold">
          Check your microphone
        </h2>
        <p className="text-sm text-muted-foreground">
          The examiner needs to hear you. Your browser will ask for permission when you start the
          check. Use headphones in a quiet room for the best result.
        </p>
        <div className="flex items-center justify-between gap-4 rounded-xl border p-4">
          <div className="space-y-1 text-sm" aria-live="polite">
            <p className="flex items-center gap-2 font-medium">
              {state === "ok" ? (
                <CheckCircle2Icon className="size-4 text-success" aria-hidden="true" />
              ) : state === "denied" || state === "unsupported" ? (
                <CircleAlertIcon className="size-4 text-destructive" aria-hidden="true" />
              ) : (
                <MicIcon className="size-4" aria-hidden="true" />
              )}
              {
                {
                  idle: "Microphone not checked yet",
                  checking: "Waiting for permission…",
                  ok: "Microphone working",
                  denied: "Microphone access was blocked",
                  unsupported: "This browser cannot record audio",
                }[state]
              }
            </p>
            {device && <p className="text-xs text-muted-foreground">Device: {device}</p>}
            {state === "ok" && (
              <p className="text-xs text-muted-foreground">Say something — the bars should move.</p>
            )}
          </div>
          <Waveform level={level} active={state === "ok"} label="Microphone level" />
        </div>
        {state === "denied" && (
          <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm">
            Allow microphone access for this site (the camera/microphone icon in the address bar),
            then try the check again.
          </p>
        )}
        {state === "unsupported" && (
          <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm">
            Use a recent version of Chrome, Edge, Firefox or Safari to take the speaking test.
          </p>
        )}
        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            onClick={() => void check()}
            disabled={state === "checking" || state === "unsupported"}
          >
            <MicIcon aria-hidden="true" />
            {state === "ok" ? "Check again" : "Start microphone check"}
          </Button>
          <Button onClick={() => enter.mutate()} disabled={state !== "ok" || enter.isPending}>
            {enter.isPending && <LoaderCircleIcon className="animate-spin" aria-hidden="true" />}
            Enter Speaking Room
          </Button>
        </div>
        <p className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
          {room.voice.message}
        </p>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------------------ transcript
export type Caption = {
  id: string;
  speaker: "examiner" | "candidate";
  text: string;
  final: boolean;
  /** Last stored transcript seq when the caption started; a stored turn after it replaces it. */
  after: number;
};

const lastSeq = (room: Room) => room.transcript.reduce((m, t) => Math.max(m, t.seq), 0);

const norm = (t: string) =>
  t
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

function Transcript({
  room,
  live,
  captions = [],
}: {
  room: Room;
  live: boolean;
  captions?: Caption[];
}) {
  const end = useRef<HTMLLIElement>(null);
  // A finished caption disappears once the backend has stored that speaker's line.
  const stored = new Set(room.transcript.slice(-12).map((t) => norm(t.text)));
  const pending = captions.filter(
    (c) =>
      c.text.trim() &&
      // (also unfinished ones: a segment whose closing stream was lost must not linger)
      !(
        (c.final && stored.has(norm(c.text))) ||
        room.transcript.some((t) => t.speaker === c.speaker && t.seq > c.after)
      ),
  );
  const merged: Caption[] = [];
  for (const c of pending) {
    const prev = merged.at(-1);
    if (prev && prev.speaker === c.speaker) {
      merged[merged.length - 1] = { ...prev, text: `${prev.text} ${c.text}`, final: c.final };
    } else merged.push(c);
  }
  const tail = merged.map((c) => c.text).join("|");
  useEffect(() => {
    if (live) end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [live, room.transcript.length, tail]);
  return (
    <ol
      className="space-y-3"
      aria-live={live ? "polite" : undefined}
      aria-label="Conversation transcript"
    >
      {room.transcript.map((t) => (
        <TurnLine key={t.seq} turn={t} room={room} />
      ))}
      {merged.map((c) => (
        <TurnLine
          key={`c-${c.id}`}
          room={room}
          live={!c.final}
          turn={
            {
              seq: -1,
              speaker: c.speaker,
              text: c.text,
              part_no: room.current_part ?? null,
              offset_ms: null,
              duration_ms: null,
              recording_id: null,
            } as unknown as RoomTurn
          }
        />
      ))}
      <li ref={end} aria-hidden="true" />
    </ol>
  );
}

function TurnLine({ turn: t, room, live = false }: { turn: RoomTurn; room: Room; live?: boolean }) {
  const examiner = t.speaker === "examiner";
  return (
    <li className={cn("flex gap-3", !examiner && "flex-row-reverse")}>
      {examiner ? (
        <ExaminerAvatar examiner={room.examiner} size="sm" />
      ) : (
        <span
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-muted font-semibold"
          aria-hidden="true"
        >
          You
        </span>
      )}
      <div
        className={cn(
          "max-w-[85%] space-y-1 rounded-2xl px-4 py-2.5 text-sm",
          examiner ? "rounded-tl-sm bg-muted" : "rounded-tr-sm bg-primary/10",
        )}
      >
        <p className="text-[0.6875rem] font-semibold tracking-wide text-muted-foreground uppercase">
          {examiner ? room.examiner.name : "You"}
          {t.part_no ? ` · Part ${t.part_no}` : ""}
          {t.offset_ms !== null ? ` · ${clockOf(t.offset_ms)}` : ""}
        </p>
        {t.text ? (
          <p className="whitespace-pre-line">
            {t.text}
            {live && <span className="ml-0.5 inline-block w-1.5 animate-pulse">▍</span>}
          </p>
        ) : (
          <p className="italic text-muted-foreground">
            Spoken answer recorded{t.duration_ms ? ` (${clockOf(t.duration_ms)})` : ""} · the
            written transcript appears after evaluation
          </p>
        )}
      </div>
    </li>
  );
}

// ------------------------------------------------------------------------------ live voice
/**
 * Live mode: joins the LiveKit room with a short-lived token from the backend, plays the AI
 * examiner's audio and publishes the candidate's microphone. The transcript comes from the backend
 * (the examiner agent posts each line), refreshed by polling; live word-by-word captions for both
 * speakers arrive on LiveKit's "lk.transcription" text streams until the stored line replaces them.
 */
function LiveVoiceStage({
  room,
  muted,
  captions,
  onCaptions,
}: {
  room: Room;
  muted: boolean;
  captions: Caption[];
  onCaptions: (update: (c: Caption[]) => Caption[]) => void;
}) {
  const lk = useRef<LiveKitRoom | null>(null);
  const audioBox = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"connecting" | "connected" | "error">("connecting");
  const [error, setError] = useState<string | null>(null);
  const [needsAudio, setNeedsAudio] = useState(false);
  const [examinerSpeaking, setExaminerSpeaking] = useState(false);
  const [youSpeaking, setYouSpeaking] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const seqRef = useRef(lastSeq(room));
  useEffect(() => {
    seqRef.current = lastSeq(room);
  });

  useEffect(() => {
    let cancelled = false;
    const r = new LiveKitRoom({ adaptiveStream: true, dynacast: true });
    lk.current = r;
    r.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) audioBox.current?.appendChild(track.attach());
    });
    r.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));
    r.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      setExaminerSpeaking(speakers.some((sp) => !sp.isLocal));
      setYouSpeaking(speakers.some((sp) => sp.isLocal));
    });
    // Word-by-word captions: the agent streams its own speech (synced to the audio) and the
    // candidate's recognised speech on the "lk.transcription" topic. Each stream carries one
    // segment; a newer stream for the same segment replaces its text.
    r.registerTextStreamHandler("lk.transcription", async (reader, from) => {
      const attrs = reader.info.attributes ?? {};
      const id = attrs["lk.segment_id"] ?? reader.info.id;
      const speaker = from.identity === r.localParticipant.identity ? "candidate" : "examiner";
      const after = seqRef.current;
      const put = (text: string, final: boolean) =>
        onCaptions((list) => {
          const prev = list.find((c) => c.id === id);
          const next = list.filter((c) => c.id !== id).slice(-20);
          return [...next, { id, speaker, text, final, after: prev?.after ?? after }];
        });
      let text = "";
      for await (const chunk of reader) {
        text += chunk;
        put(text, false);
      }
      put(text, reader.info.attributes?.["lk.transcription_final"] === "true");
    });
    r.on(RoomEvent.AudioPlaybackStatusChanged, () => setNeedsAudio(!r.canPlaybackAudio));
    r.on(RoomEvent.Disconnected, () => {
      if (!cancelled) setState("error");
    });
    (async () => {
      try {
        const c = await fetchVoiceToken(room.id);
        if (cancelled) return;
        await r.connect(c.url, c.token);
        await r.localParticipant.setMicrophoneEnabled(true);
        try {
          await r.startAudio();
        } catch {
          setNeedsAudio(true);
        }
        if (!cancelled) setState("connected");
      } catch (e) {
        if (!cancelled) {
          setError(messageFor(e));
          setState("error");
        }
      }
    })();
    return () => {
      cancelled = true;
      void r.disconnect();
    };
  }, [room.id, onCaptions]);

  useEffect(() => {
    void lk.current?.localParticipant.setMicrophoneEnabled(!muted).catch(() => undefined);
  }, [muted]);

  const phase = room.live_phase;
  const timed = phase && (phase.phase === "prep" || phase.phase === "long_turn") && phase.seconds;
  useEffect(() => {
    if (!timed) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [timed]);
  const left = timed
    ? Math.max(0, phase.seconds! - Math.floor((now - Date.parse(phase.since)) / 1000))
    : 0;
  const liveExaminer = [...captions].reverse().find((c) => c.speaker === "examiner");
  const liveYou = [...captions].reverse().find((c) => c.speaker === "candidate" && !c.final);
  const lastExaminer =
    liveExaminer ?? [...room.transcript].reverse().find((t) => t.speaker === "examiner");
  const card = room.current_part === 2 ? room.cue_card : null;

  return (
    <div className="w-full max-w-xl space-y-3" aria-live="polite">
      <div ref={audioBox} hidden />
      <p className="text-xs font-semibold tracking-wide text-primary uppercase">
        {state === "connecting"
          ? "Connecting to your examiner…"
          : state === "error"
            ? "Connection lost"
            : phase?.phase === "prep" && left > 0
              ? "Preparation time — plan what you will say"
              : examinerSpeaking
                ? `${room.examiner.name} is speaking`
                : youSpeaking
                  ? "You are speaking"
                  : "Listening…"}
      </p>
      {state === "connected" && (
        <div className="flex items-center justify-center gap-6">
          {youSpeaking && !examinerSpeaking ? (
            <span
              className="inline-flex size-14 items-center justify-center rounded-full bg-primary/15 font-semibold text-primary ring-2 ring-primary/50"
              aria-hidden="true"
            >
              You
            </span>
          ) : (
            <ExaminerAvatar examiner={room.examiner} size="md" speaking={examinerSpeaking} />
          )}
          <Waveform
            level={youSpeaking && !muted ? 0.45 : 0}
            active={youSpeaking && !muted}
            label="Your voice activity"
          />
        </div>
      )}
      {lastExaminer && !card && (
        <p className="font-heading text-lg leading-snug">{lastExaminer.text}</p>
      )}
      {liveYou && (
        <p className="text-sm text-muted-foreground italic">
          <span className="font-semibold not-italic">You: </span>
          {liveYou.text}
        </p>
      )}
      {card && (
        <div className="rounded-2xl border-2 border-dashed bg-background p-4 text-left">
          <p className="font-medium">{card.prompt}</p>
          {card.points.length > 0 && (
            <>
              <p className="mt-2 text-sm">You should say:</p>
              <ul className="list-disc pl-6 text-sm">
                {card.points.map((pt) => (
                  <li key={pt}>{pt}</li>
                ))}
              </ul>
            </>
          )}
          {card.closing && <p className="mt-1 text-sm">{card.closing}</p>}
        </div>
      )}
      {timed && left > 0 && (
        <p
          className="font-mono text-4xl font-semibold tabular-nums"
          aria-label={`${left} seconds left`}
        >
          {clockOf(left * 1000)}
        </p>
      )}
      {needsAudio && (
        <Button onClick={() => void lk.current?.startAudio().then(() => setNeedsAudio(false))}>
          Click to hear the examiner
        </Button>
      )}
      {state === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {error ?? "The voice connection dropped. Reload the page to reconnect."}
        </p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------ live room
type Phase = "examiner" | "prep" | "recording" | "processing" | "retry";

/** One candidate answer step (keyed by step): examiner line -> optional prep -> recording. */
function AnswerStage({
  room,
  stream,
  muted,
  level,
  onUpdate,
  registerStop,
}: {
  room: Room;
  stream: MediaStream | null;
  muted: boolean;
  level: number;
  onUpdate: (r: Room) => void;
  registerStop: (stop: () => void) => void;
}) {
  const current = room.current!;
  const [phase, setPhase] = useState<Phase>("examiner");
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const started = useRef(0);
  const lastExaminer = [...room.transcript].reverse().find((t) => t.speaker === "examiner");

  const finish = useCallback(() => {
    const rec = recorder.current;
    if (rec && rec.state !== "inactive") rec.stop();
  }, []);

  const beginRecording = useCallback(() => {
    if (!stream) {
      setError("The microphone is not available.");
      setPhase("retry");
      return;
    }
    const mime = preferredMime();
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks.current = [];
    rec.ondataavailable = (e) => {
      if (e.data.size) chunks.current.push(e.data);
    };
    rec.onstop = async () => {
      const blob = new Blob(chunks.current, { type: (rec.mimeType || mime).split(";")[0] });
      const duration = Date.now() - started.current;
      if (duration < 1500 || blob.size === 0) {
        setError("We did not catch an answer. Try again.");
        setPhase("retry");
        return;
      }
      setPhase("processing");
      try {
        await uploadRecording(
          room.id,
          { part_no: current.part_no as 1 | 2 | 3, question_no: current.question_no },
          blob,
          duration,
        );
        onUpdate(await advanceRoom(room.id, current.step));
      } catch (e) {
        setError(messageFor(e));
        setPhase("retry");
      }
    };
    recorder.current = rec;
    started.current = Date.now();
    rec.start(1000);
    setError(null);
    setLeft(current.answer_seconds);
    setPhase("recording");
  }, [stream, room.id, current, onUpdate]);

  useEffect(() => {
    registerStop(() => {
      const rec = recorder.current;
      if (rec && rec.state !== "inactive") {
        rec.onstop = null;
        rec.stop();
      }
    });
  }, [registerStop]);

  // The examiner's line stays on screen long enough to read, then the candidate's turn begins.
  useEffect(() => {
    const words = lastExaminer?.text.split(/\s+/).length ?? 10;
    const t = setTimeout(
      () => {
        if (current.prep_seconds > 0) {
          setLeft(current.prep_seconds);
          setPhase("prep");
        } else beginRecording();
      },
      Math.min(6000, 1200 + words * 120),
    );
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per step (component is keyed)
  }, []);

  // Pause the recorder while muted.
  useEffect(() => {
    const rec = recorder.current;
    if (!rec) return;
    if (muted && rec.state === "recording") rec.pause();
    if (!muted && rec.state === "paused") rec.resume();
  }, [muted]);

  // Preparation and answer countdowns.
  useEffect(() => {
    if (phase !== "prep" && phase !== "recording") return;
    if (muted && phase === "recording") return;
    const t = setTimeout(() => {
      if (left > 1) setLeft(left - 1);
      else if (phase === "prep") beginRecording();
      else {
        setLeft(0);
        finish();
      }
    }, 1000);
    return () => clearTimeout(t);
  }, [phase, left, muted, finish, beginRecording]);

  const status: Record<Phase, string> = {
    examiner: `${room.examiner.name} is speaking`,
    prep: "Preparation time — plan what you will say",
    recording: muted ? "Microphone muted — recording paused" : "Your turn — speak now",
    processing: "Processing your answer…",
    retry: "Something went wrong with that answer",
  };
  const card = current.cue_card;
  return (
    <>
      <div className="w-full max-w-xl space-y-3" aria-live="polite">
        <p className="text-xs font-semibold tracking-wide text-primary uppercase">
          {status[phase]}
        </p>
        {phase === "examiner" && lastExaminer && (
          <p className="font-heading text-xl leading-snug">{lastExaminer.text}</p>
        )}
        {(phase === "prep" || phase === "recording") && card && (
          <div className="rounded-2xl border-2 border-dashed bg-background p-4 text-left">
            <p className="font-medium">{card.prompt}</p>
            {card.points.length > 0 && (
              <>
                <p className="mt-2 text-sm">You should say:</p>
                <ul className="list-disc pl-6 text-sm">
                  {card.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </>
            )}
            {card.closing && <p className="mt-1 text-sm">{card.closing}</p>}
          </div>
        )}
        {phase === "recording" && !card && lastExaminer && (
          <p className="text-sm text-muted-foreground">{lastExaminer.text}</p>
        )}
        {(phase === "prep" || phase === "recording") && (
          <p
            className="font-mono text-4xl font-semibold tabular-nums"
            aria-label={`${left} seconds left`}
          >
            {clockOf(left * 1000)}
          </p>
        )}
        {phase === "recording" && (
          <div className="flex justify-center">
            <Waveform level={level} active={!muted} label="Your voice level" />
          </div>
        )}
        {phase === "processing" && (
          <LoaderCircleIcon
            className="mx-auto size-8 animate-spin text-primary"
            aria-hidden="true"
          />
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        {phase === "prep" && (
          <Button variant="outline" onClick={beginRecording}>
            I&apos;m ready — start speaking
          </Button>
        )}
        {phase === "recording" && (
          <Button onClick={finish}>
            <SquareIcon aria-hidden="true" />
            Finish my answer
          </Button>
        )}
        {phase === "retry" && (
          <Button onClick={beginRecording}>
            <RotateCcwIcon aria-hidden="true" />
            Answer again
          </Button>
        )}
      </div>
    </>
  );
}

function LiveRoom({ room, onUpdate }: { room: Room; onUpdate: (r: Room) => void }) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [showTranscript, setShowTranscript] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const stopAnswer = useRef<() => void>(() => {});
  const level = useLevel(stream);
  const registerStop = useCallback((stop: () => void) => {
    stopAnswer.current = stop;
  }, []);

  useEffect(() => {
    let mine: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((s) => {
        mine = s;
        setStream(s);
      })
      .catch(() => setMicError("Microphone access was lost. Allow it and reload the page."));
    return () => mine?.getTracks().forEach((t) => t.stop());
  }, []);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  function toggleMute() {
    const next = !muted;
    stream?.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMuted(next);
  }

  const end = useMutation({
    mutationFn: () => endRoom(room.id),
    onSuccess: (r) => {
      stopAnswer.current();
      onUpdate(r);
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const elapsed = room.started_at ? now - Date.parse(room.started_at) : 0;
  const limit = (room.timing.max_total_minutes ?? 15) * 60_000;
  const live = room.voice.mode === "live";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-card px-4 py-3">
        <div className="flex flex-wrap items-center gap-2" aria-label="Test progress">
          {[1, 2, 3].map((p) => (
            <span
              key={p}
              aria-current={room.current_part === p ? "step" : undefined}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-semibold",
                room.current_part === p
                  ? "bg-primary text-primary-foreground"
                  : (room.current_part ?? 0) > p
                    ? "bg-success/15 text-success"
                    : "bg-muted text-muted-foreground",
              )}
            >
              Part {p}
            </span>
          ))}
          {!live && (
            <span className="text-xs text-muted-foreground">
              {room.answers_done}/{room.answers_total} answers
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span
            className={cn("font-mono tabular-nums", elapsed > limit && "text-warning")}
            aria-label="Session time"
          >
            {clockOf(elapsed)} / {clockOf(limit)}
          </span>
          <span className="flex items-center gap-1.5 text-xs" title={room.voice.message}>
            <WifiIcon
              className={cn("size-4", micError ? "text-destructive" : "text-success")}
              aria-hidden="true"
            />
            {live ? "Live examiner" : "Guided mode"}
          </span>
          <span className="flex items-center gap-1.5 text-xs">
            {muted ? (
              <MicOffIcon className="size-4" aria-hidden="true" />
            ) : (
              <MicIcon className="size-4 text-success" aria-hidden="true" />
            )}
            {micError ? "Microphone unavailable" : muted ? "Muted" : "Microphone on"}
          </span>
        </div>
      </header>

      <div className={cn("grid gap-4", showTranscript && "lg:grid-cols-[1.25fr_1fr]")}>
        <section
          aria-label="Conversation"
          className="flex min-h-[28rem] flex-col items-center justify-between gap-6 rounded-3xl border bg-gradient-to-b from-primary/10 via-card to-card p-6 text-center shadow-elevation-1"
        >
          <div className="flex w-full items-start justify-between gap-6">
            <div className="flex flex-1 flex-col items-center gap-2">
              <ExaminerAvatar examiner={room.examiner} size="lg" />
              <p className="text-sm font-medium">{room.examiner.name}</p>
            </div>
            <div className="flex flex-1 flex-col items-center gap-2">
              <span className="relative inline-flex size-20 items-center justify-center rounded-full border-4 border-muted bg-background">
                {muted ? (
                  <MicOffIcon className="size-8 text-muted-foreground" aria-hidden="true" />
                ) : (
                  <MicIcon className="size-8" aria-hidden="true" />
                )}
              </span>
              <p className="text-sm font-medium">You</p>
            </div>
          </div>
          {micError && (
            <p role="alert" className="text-sm text-destructive">
              {micError}
            </p>
          )}
          {live ? (
            <LiveVoiceStage
              room={room}
              muted={muted}
              captions={captions}
              onCaptions={setCaptions}
            />
          ) : room.current ? (
            <AnswerStage
              key={room.current.step}
              room={room}
              stream={stream}
              muted={muted}
              level={level}
              onUpdate={onUpdate}
              registerStop={registerStop}
            />
          ) : (
            <LoaderCircleIcon className="size-8 animate-spin text-primary" aria-hidden="true" />
          )}
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button
              variant="outline"
              size="icon"
              onClick={toggleMute}
              aria-pressed={muted}
              aria-label={muted ? "Unmute microphone" : "Mute microphone"}
            >
              {muted ? <MicOffIcon aria-hidden="true" /> : <MicIcon aria-hidden="true" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setShowTranscript((v) => !v)}
              aria-pressed={showTranscript}
              aria-label={showTranscript ? "Hide transcript" : "Show transcript"}
            >
              {showTranscript ? <EyeOffIcon aria-hidden="true" /> : <EyeIcon aria-hidden="true" />}
            </Button>
            <Button variant="destructive" onClick={() => setConfirmEnd(true)}>
              <PhoneOffIcon aria-hidden="true" />
              End session
            </Button>
          </div>
        </section>
        {showTranscript && (
          <section
            aria-labelledby="tr-h"
            className="flex max-h-[36rem] flex-col rounded-3xl border bg-card"
          >
            <h2 id="tr-h" className="border-b px-5 py-3 font-heading text-base font-semibold">
              Live transcript
            </h2>
            <div className="flex-1 overflow-y-auto p-4">
              <Transcript room={room} live captions={live ? captions : undefined} />
            </div>
          </section>
        )}
      </div>

      <Dialog open={confirmEnd} onOpenChange={(o) => !end.isPending && setConfirmEnd(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>End the speaking session?</DialogTitle>
            <DialogDescription>
              The answers you have recorded so far are kept and sent for evaluation. You cannot
              continue this session afterwards.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmEnd(false)}>
              Keep going
            </Button>
            <Button variant="destructive" onClick={() => end.mutate()} disabled={end.isPending}>
              End session
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------------------------ completed
function CompletedRoom({ room }: { room: Room }) {
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: () => retrySpeakingEvaluation(room.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY(room.id) }),
    onError: (e) => toast.error(messageFor(e)),
  });
  const e = room.evaluation;
  const succeeded = e?.status === "succeeded";
  return (
    <div className="space-y-8">
      <section className="flex flex-wrap items-center gap-5 rounded-3xl border bg-gradient-to-br from-success/10 via-card to-card p-6 shadow-elevation-1">
        <ExaminerAvatar examiner={room.examiner} size="lg" />
        <div className="flex-1 space-y-1">
          <h1 className="font-heading text-2xl font-semibold">Session complete</h1>
          <p className="text-sm text-muted-foreground">
            {room.test_title} with {room.examiner.name} ·{" "}
            {clockOf((room.duration_seconds ?? 0) * 1000)} · {room.answers_done} of{" "}
            {room.answers_total} answers
            {room.completion_reason === "ended_by_candidate" && " · ended early"}
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href="/speaking/start">Practise again</Link>
        </Button>
      </section>

      {!e ? (
        <p className="rounded-2xl border border-dashed p-6 text-sm text-muted-foreground">
          No answers were recorded, so there is nothing to evaluate.
        </p>
      ) : !succeeded && !isPending(e) ? (
        <div className="space-y-2">
          <h2 className="font-heading text-xl font-semibold">Evaluation Pending</h2>
          <EvaluationView
            evaluation={e}
            retrying={retry.isPending}
            onRetry={() => retry.mutate()}
          />
        </div>
      ) : (
        <EvaluationView evaluation={e} retrying={retry.isPending} onRetry={() => retry.mutate()} />
      )}

      <section aria-labelledby="full-tr" className="space-y-3">
        <h2 id="full-tr" className="font-heading text-xl font-semibold">
          Full transcript
        </h2>
        <div className="rounded-3xl border bg-card p-5">
          {room.transcript.length ? (
            <Transcript room={room} live={false} />
          ) : (
            <p className="text-sm text-muted-foreground">No conversation was recorded.</p>
          )}
        </div>
        {room.transcript.some((t) => t.recording_id) && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">Listen to your answers</h3>
            <ul className="grid gap-2 md:grid-cols-2">
              {room.transcript
                .filter((t) => t.recording_id)
                .map((t, i) => (
                  <li key={t.seq} className="space-y-1 rounded-xl border p-3 text-sm">
                    <p className="text-xs text-muted-foreground">
                      Part {t.part_no} · answer {i + 1}
                    </p>
                    <Playback sessionId={room.id} recordingId={t.recording_id!} />
                  </li>
                ))}
            </ul>
          </div>
        )}
      </section>
      <ModelAnswers answers={room.model_answers} />
    </div>
  );
}

// ------------------------------------------------------------------------------ page
export function SpeakingRoom({ roomId }: { roomId: string }) {
  const qc = useQueryClient();
  const room = useQuery({
    queryKey: KEY(roomId),
    queryFn: () => fetchRoom(roomId),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (d?.status === "live" && d.voice.mode === "live") return 1500; // live transcript
      return d?.status === "completed" && isPending(d.evaluation) ? 3000 : false;
    },
  });
  const set = (r: Room) => qc.setQueryData(KEY(roomId), r);
  if (room.isPending) return <LoadingState label="Opening your speaking room…" />;
  if (room.isError)
    return (
      <ErrorState
        title="This speaking room could not be opened"
        description={messageFor(room.error)}
        action={
          <Button asChild variant="outline">
            <Link href="/speaking">Back to Speaking</Link>
          </Button>
        }
      />
    );
  const r = room.data;
  if (r.status === "created") return <WaitingRoom room={r} onEntered={set} />;
  if (r.status === "live") return <LiveRoom key={r.id} room={r} onUpdate={set} />;
  return <CompletedRoom room={r} />;
}
