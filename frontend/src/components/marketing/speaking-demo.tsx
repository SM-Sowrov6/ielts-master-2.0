"use client";

import { MicIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { loopWhileVisible, useReducedMotion } from "@/components/marketing/demo-motion";
import { TiltScene } from "@/components/marketing/tilt-scene";

/* The sample exchange (Part 1). */
type Who = "ai" | "you";
export const CONVERSATION: readonly { who: Who; text: string; time: string }[] = [
  {
    who: "ai",
    text: "Let's talk about your hometown. What do you like most about the place where you live?",
    time: "00:04",
  },
  {
    who: "you",
    text: "I really enjoy the peaceful environment and the friendly community in my hometown.",
    time: "00:11",
  },
];
const WORDS = CONVERSATION.map((line) => line.text.split(" "));

/** idle → ai (partner speaks) → handoff → you (student answers) → done → loop. */
export type Turn = "idle" | "ai" | "handoff" | "you" | "done";

/** Pause after a word: longer at commas and sentence ends, like natural speech. */
const pauseAfter = (word: string, who: Who) =>
  (who === "ai" ? 170 : 230) + (/[.?!]$/.test(word) ? 380 : /,$/.test(word) ? 220 : 0);

/**
 * The AI Speaking Partner scene with its looping demonstration. One timeline drives everything:
 * the partner speaks (mouth, blue waveform, its bubble's words appear), hands over, the
 * microphone shows "Your Turn" and glows, the student's answer appears word by word with the
 * emerald waveform while the partner listens attentively, then a short hold and a smooth fade
 * back to the start. Visual demonstration only: no microphone access or audio. Runs only while
 * on screen; with prefers-reduced-motion the finished exchange is shown without motion.
 * Decorative: rendered inside an aria-hidden, inert container.
 */
export function SpeakingDemo() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [turn, setTurn] = useState<Turn>("idle");
  const [line, setLine] = useState(-1);
  const [words, setWords] = useState(0);
  const [fading, setFading] = useState(false);
  const finished = useReducedMotion();

  useEffect(() => {
    if (finished) return;
    return loopWhileVisible(rootRef.current, async (wait) => {
      setTurn("idle");
      setLine(-1);
      setWords(0);
      await wait(60);
      setFading(false);
      await wait(900);

      for (let i = 0; i < CONVERSATION.length; i += 1) {
        const who = CONVERSATION[i]?.who ?? "ai";
        const lineWords = WORDS[i] ?? [];
        setTurn(who);
        await wait(who === "you" ? 700 : 350); // the mic opens / the partner draws breath
        setLine(i);
        setWords(0);
        for (let w = 1; w <= lineWords.length; w += 1) {
          setWords(w);
          await wait(pauseAfter(lineWords[w - 1] ?? "", who));
        }
        await wait(400);
        if (who === "ai") {
          setTurn("handoff");
          await wait(700);
        }
      }

      setTurn("done");
      await wait(3200);
      setFading(true);
      await wait(800);
    });
  }, [finished]);

  const shownTurn: Turn = finished ? "done" : turn;
  const shownLine = finished ? CONVERSATION.length - 1 : line;
  const shownWords = finished ? (WORDS.at(-1)?.length ?? 0) : words;
  const status: Record<Turn, string> = {
    idle: "Ready to start",
    ai: "AI partner is speaking",
    handoff: "Your turn next",
    you: "Listening to you",
    done: "Conversation complete",
  };

  return (
    <div
      ref={rootRef}
      className="sx-demo"
      data-turn={shownTurn}
      data-fading={!finished && fading}
      data-static={finished}
    >
      <TiltScene className="sx-scene">
        <div className="sx-floor" />
        <div className="sx-layout">
          <div className="sx-side sx-side-ai">
            <Avatar />
            <span className="sx-label sx-label-ai">
              <MiniBot />
              AI speaking partner
            </span>
          </div>

          <div className="sx-center">
            <div className="sx-panel">
              <div className="flex items-center gap-2.5 border-b px-4 py-3">
                <span className="sx-live-dot" />
                <span className="text-sm font-semibold">Live conversation</span>
                <span className="sx-panel-part text-xs text-muted-foreground">
                  Part 1 · Interview
                </span>
                <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground">
                  Sample
                </span>
              </div>
              <div className="sx-transcript">
                {CONVERSATION.map((entry, i) => {
                  if (i > shownLine) return null;
                  const count = i < shownLine ? (WORDS[i]?.length ?? 0) : shownWords;
                  const live = i === shownLine && shownTurn === entry.who;
                  return (
                    <div key={i} className="sx-bubble" data-who={entry.who} data-live={live}>
                      <span className="sx-avatar-dot">
                        {entry.who === "ai" ? <MiniBot /> : <MicIcon className="size-3.5" />}
                      </span>
                      <div className="min-w-0">
                        <span className="sx-bubble-meta">
                          {entry.who === "ai" ? "AI partner" : "You"}
                          <span className="tabular-nums">{entry.time}</span>
                        </span>
                        <p className="sx-bubble-text">
                          {WORDS[i]?.slice(0, count).join(" ")}
                          {live && <span className="sx-speaking" />}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center gap-2.5 border-t px-4 py-2.5 text-xs text-muted-foreground">
                <span className="sx-status-dot" />
                <span className="sx-status">{status[shownTurn]}</span>
              </div>
            </div>
            <VoiceWaves />
          </div>

          <div className="sx-side sx-side-you">
            <Microphone />
            <span className="sx-label sx-label-you">
              <span className="sx-rec" />
              Your Turn
            </span>
          </div>
        </div>
      </TiltScene>
    </div>
  );
}

/* Waveform: a seamless sine path twice the visible width, slid left; layered for depth. */
function sinePath(period: number, amplitude: number, width = 2400, mid = 50) {
  const points: string[] = [];
  for (let x = 0; x <= width; x += 10) {
    const y = mid + amplitude * Math.sin((x / period) * Math.PI * 2);
    points.push(`${x},${y.toFixed(1)}`);
  }
  return `M${points.join(" L")}`;
}
const LAYERS = [
  { period: 240, amplitude: 34, width: 3, speed: "3.2s", opacity: 1 },
  { period: 150, amplitude: 22, width: 2, speed: "2.1s", opacity: 0.6 },
  { period: 400, amplitude: 40, width: 7, speed: "4.6s", opacity: 0.18 },
].map((layer) => ({ ...layer, d: sinePath(layer.period, layer.amplitude) }));

function VoiceWaves() {
  return (
    <div className="sx-waves">
      <div className="sx-wave-track">
        {(["ai", "you"] as const).map((tone) => (
          <div key={tone} className="sx-wave" data-tone={tone}>
            {LAYERS.map((layer, i) => (
              <div
                key={i}
                className="sx-wave-layer"
                style={{ animationDuration: layer.speed, opacity: layer.opacity }}
              >
                <svg viewBox="0 0 2400 100" preserveAspectRatio="none">
                  <path d={layer.d} strokeWidth={layer.width} vectorEffect="non-scaling-stroke" />
                </svg>
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="sx-wave-legend">
        <span data-tone="ai">
          <i /> AI Speaking
        </span>
        <span data-tone="you">
          Your Speaking <i />
        </span>
      </div>
    </div>
  );
}

/** A tiny version of the partner's face, used as its badge in the label and the transcript. */
function MiniBot() {
  return (
    <span className="sx-minibot">
      <span className="sx-minibot-visor">
        <i />
        <i />
      </span>
    </span>
  );
}

/** The AI partner: a glossy 3D bust with a glass visor, halo and pedestal (CSS only). */
function Avatar() {
  return (
    <div className="sx-avatar">
      <span className="sx-shadow" />
      <span className="sx-pedestal">
        <span className="sx-pedestal-ring" />
      </span>
      <span className="sx-body">
        <span className="sx-torso">
          <span className="sx-collar" />
          <span className="sx-core" />
        </span>
        <span className="sx-neck" />
        <span className="sx-head">
          <span className="sx-ear sx-ear-l" />
          <span className="sx-ear sx-ear-r" />
          <span className="sx-visor">
            <span className="sx-eyes">
              <span className="sx-eye" />
              <span className="sx-eye" />
            </span>
            <span className="sx-mouth" />
          </span>
          <span className="sx-shine" />
        </span>
      </span>
    </div>
  );
}

/** A studio microphone: grille capsule, band, body, yoke and stand, with a sound ring. */
function Microphone() {
  return (
    <div className="sx-mic">
      <span className="sx-mic-shadow" />
      <span className="sx-mic-base" />
      <span className="sx-mic-pole" />
      <span className="sx-mic-float">
        <span className="sx-mic-ring" />
        <span className="sx-mic-ring sx-mic-ring-2" />
        <span className="sx-mic-yoke" />
        <span className="sx-mic-body">
          <span className="sx-mic-led" />
        </span>
        <span className="sx-mic-head">
          <span className="sx-mic-grille" />
          <span className="sx-mic-band" />
        </span>
      </span>
    </div>
  );
}
