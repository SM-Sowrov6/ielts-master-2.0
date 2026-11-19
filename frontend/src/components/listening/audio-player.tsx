"use client";

import { LoaderCircleIcon, PauseIcon, PlayIcon, RotateCcwIcon, Volume2Icon } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchAudio, type Audio } from "@/lib/exam/api";
import { messageFor } from "@/lib/auth/api";
import { formatClock } from "@/lib/exam/responses";

/**
 * Section recording player (remounted per section by its parent's `key`). The URL is requested from the server only when the candidate presses
 * play (in exam mode that request starts the single play; a reload resumes at the server-side
 * elapsed offset instead of restarting). Exam mode: no seeking, no pause, no replay. Practice:
 * full controls. The signed URL is short-lived and never stored; on a playback error a fresh one
 * is requested and playback continues where it stopped.
 */
export function AudioPlayer({
  attemptId,
  sectionNo,
  exam,
  hasAudio,
}: {
  attemptId: string;
  sectionNo: number;
  exam: boolean;
  hasAudio: boolean;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const [grant, setGrant] = useState<Audio | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "playing" | "paused" | "ended" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const resumeAt = useRef(0);

  const load = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const next = await fetchAudio(attemptId, sectionNo);
      resumeAt.current = Math.max(resumeAt.current, next.offset_ms / 1000);
      setGrant(next);
    } catch (e) {
      setError(messageFor(e));
      setState("error");
    }
  }, [attemptId, sectionNo]);

  useEffect(() => {
    const el = audio.current;
    if (!el || !grant) return;
    el.src = grant.url;
    el.volume = volume;
    const start = () => {
      if (resumeAt.current > 0 && Number.isFinite(el.duration)) {
        if (resumeAt.current >= el.duration) {
          setState("ended");
          return;
        }
        el.currentTime = resumeAt.current;
      }
      void el.play().catch(() => {
        setState("paused"); // autoplay blocked: the candidate presses play
      });
    };
    el.addEventListener("loadedmetadata", start, { once: true });
    el.load();
    return () => el.removeEventListener("loadedmetadata", start);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- volume is applied separately
  }, [grant]);

  useEffect(() => {
    if (audio.current) audio.current.volume = volume;
  }, [volume]);

  if (!hasAudio) {
    return (
      <p className="rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        This part has no recording.
      </p>
    );
  }

  const playing = state === "playing";
  const canControl = !exam;
  return (
    <div
      className="space-y-2 rounded-xl border bg-card p-4 shadow-elevation-1"
      aria-label={`Recording for part ${sectionNo}`}
      role="group"
    >
      <audio
        ref={audio}
        preload="none"
        onPlay={() => setState("playing")}
        onPause={() => setState((s) => (s === "ended" ? s : "paused"))}
        onEnded={() => setState("ended")}
        onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
        onDurationChange={(e) => setDuration(e.currentTarget.duration)}
        onError={() => {
          if (!grant) return;
          // Signed URL expired or the network dropped: get a new one and continue.
          resumeAt.current = audio.current?.currentTime ?? resumeAt.current;
          setError("Reconnecting to the recording…");
          void load();
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        {state === "idle" || state === "error" ? (
          <Button onClick={() => void load()}>
            <PlayIcon aria-hidden="true" />
            {state === "error" ? "Try again" : exam ? "Start recording" : "Play recording"}
          </Button>
        ) : state === "loading" ? (
          <Button disabled>
            <LoaderCircleIcon className="animate-spin" aria-hidden="true" />
            Loading recording…
          </Button>
        ) : canControl ? (
          <Button
            variant="outline"
            size="icon"
            aria-label={playing ? "Pause" : state === "ended" ? "Play again" : "Play"}
            onClick={() => {
              const el = audio.current;
              if (!el) return;
              if (playing) el.pause();
              else {
                if (state === "ended") el.currentTime = 0;
                void el.play();
              }
            }}
          >
            {playing ? (
              <PauseIcon aria-hidden="true" />
            ) : state === "ended" ? (
              <RotateCcwIcon aria-hidden="true" />
            ) : (
              <PlayIcon aria-hidden="true" />
            )}
          </Button>
        ) : state === "paused" ? (
          <Button onClick={() => void audio.current?.play()}>
            <PlayIcon aria-hidden="true" />
            Continue recording
          </Button>
        ) : null}
        <div className="flex min-w-[12rem] flex-1 items-center gap-2">
          <span className="text-xs tabular-nums text-muted-foreground">
            {formatClock(time * 1000)}
          </span>
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.5}
            value={time}
            disabled={!canControl || !grant}
            aria-label="Recording position"
            aria-valuetext={`${formatClock(time * 1000)} of ${formatClock(duration * 1000)}`}
            onChange={(e) => {
              if (audio.current && canControl) audio.current.currentTime = Number(e.target.value);
            }}
            className="h-2 flex-1 accent-[var(--primary)] disabled:opacity-70"
          />
          <span className="text-xs tabular-nums text-muted-foreground">
            {duration ? formatClock(duration * 1000) : "--:--"}
          </span>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Volume2Icon className="size-4" aria-hidden="true" />
          <span className="sr-only">Volume</span>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            className="w-24 accent-[var(--primary)]"
          />
        </label>
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {error
          ? error
          : state === "ended"
            ? exam
              ? "The recording for this part has finished."
              : "Finished. You can play it again."
            : exam
              ? "Exam mode: the recording plays once and cannot be paused or rewound."
              : "Practice mode: pause, rewind and replay as often as you like."}
      </p>
    </div>
  );
}
