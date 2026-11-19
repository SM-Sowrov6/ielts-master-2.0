"use client";

import {
  BookAIcon,
  CheckIcon,
  Clock3Icon,
  GraduationCapIcon,
  SpellCheck2Icon,
  TrendingUpIcon,
} from "lucide-react";
import { memo, useEffect, useRef, useState, type CSSProperties, type RefObject } from "react";

import {
  Cancelled,
  localPoint,
  loopWhileVisible,
  useReducedMotion,
} from "@/components/marketing/demo-motion";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { cn } from "@/lib/utils";

/* Original sample essay, typed live: two paragraphs separated by a Return key press. */
const PARAGRAPHS = [
  "Remote work has become an everyday arrangement for millions of people. Although it has some drawbacks, I believe its advantages are far greater.",
  "The main benefit is time. Without a daily commute, employees can rest more and often focus better.",
] as const;
export const DEMO_TEXT = PARAGRAPHS.join("\n");
const countWords = (text: string) => text.split(/\s+/).filter(Boolean).length;
export const DEMO_WORDS = countWords(DEMO_TEXT);
const FIRST_LENGTH = PARAGRAPHS[0].length;
const TARGET_WORDS = 250;
const PLAN = ["Introduction", "Body paragraph 1", "Body paragraph 2", "Conclusion"] as const;

/* Keyboard: [id, label, width]. Ids are what `keysFor` returns for a typed character. */
type KeyDef = readonly [id: string, label: string, grow?: number];
const letters = (row: string): KeyDef[] => [...row].map((c): KeyDef => [c, c.toUpperCase()]);
const KEYBOARD: readonly (readonly KeyDef[])[] = [
  [
    ["esc", "esc", 1.5],
    ...Array.from({ length: 12 }, (_, i): KeyDef => [`f${i + 1}`, `F${i + 1}`]),
    ["power", "", 1],
  ],
  [
    ["`", "`"],
    ...[..."1234567890"].map((c): KeyDef => [c, c]),
    ["-", "-"],
    ["=", "="],
    ["delete", "delete", 1.6],
  ],
  [["tab", "tab", 1.6], ...letters("qwertyuiop"), ["[", "["], ["]", "]"], ["\\", "\\"]],
  [
    ["caps", "caps lock", 1.9],
    ...letters("asdfghjkl"),
    [";", ";"],
    ["'", "'"],
    ["return", "return", 1.9],
  ],
  [
    ["shiftL", "shift", 2.45],
    ...letters("zxcvbnm"),
    [",", ","],
    [".", "."],
    ["/", "/"],
    ["shiftR", "shift", 2.45],
  ],
  [
    ["fn", "fn"],
    ["ctrl", "control"],
    ["optL", "option"],
    ["cmdL", "command", 1.3],
    ["space", "", 5.4],
    ["cmdR", "command", 1.3],
    ["optR", "option"],
    ["left", "◀"],
    ["updown", "▲▼"],
    ["right", "▶"],
  ],
];

/** The key(s) pressed to type `ch`: the character's key, plus shift for capitals. */
export function keysFor(ch: string): string[] {
  if (ch === " ") return ["space"];
  if (ch === "\n") return ["return"];
  const lower = ch.toLowerCase();
  if (lower !== ch) return [lower, "shiftL"];
  return [ch];
}

/** Pause after typing character `i` (1-based): longer after punctuation and between words. */
const gapAfter = (ch: string, i: number) =>
  ch === "." || ch === "," ? 140 : ch === " " ? 30 : (i * 37) % 22;

/** Time a key stays down for one character. */
const STEP_MS = 52;

type Mood = "idle" | "watching" | "pause" | "done";
type Gaze = { fx: number; fy: number };
const NEUTRAL: Gaze = { fx: 0.95, fy: 0 };

/**
 * The Writing showcase MacBook with its looping demonstration: every character is typed by a key
 * press on the keyboard and appears on screen in the same step; the caret and word count follow,
 * paragraphs end with a pause and a Return press; the AI mascot on the lid watches the caret and
 * nods when the essay is done. One timeline drives keyboard, screen, counters and mascot. Runs
 * only while on screen; with prefers-reduced-motion the finished state is shown without motion.
 * Decorative: rendered inside an aria-hidden, inert container.
 */
export function WritingDemo() {
  const screenRef = useRef<HTMLDivElement>(null);
  const caretRef = useRef<HTMLSpanElement>(null);
  const firstParaRef = useRef<HTMLParagraphElement>(null);
  const botRef = useRef<HTMLDivElement>(null);

  const [awake, setAwake] = useState(false);
  const [typed, setTyped] = useState(0);
  const keyboardRef = useRef<HTMLDivElement>(null);
  const [mood, setMood] = useState<Mood>("idle");
  const [grammar, setGrammar] = useState(false);
  const [fading, setFading] = useState(false);
  const finished = useReducedMotion();

  useEffect(() => {
    if (finished) return;
    const look = ({ fx, fy }: Gaze) => {
      const bot = botRef.current;
      if (!bot) return;
      bot.style.setProperty("--fx", fx.toFixed(3));
      bot.style.setProperty("--fy", fy.toFixed(3));
    };
    const gazeAt = (el: HTMLElement | null, fx = 0, fy = 0.5): Gaze => {
      const screen = screenRef.current;
      if (!el || !screen) throw new Cancelled();
      const p = localPoint(el, screen, fx, fy);
      return { fx: p.x / screen.offsetWidth, fy: p.y / screen.offsetHeight };
    };

    let pressed: HTMLElement[] = [];
    const setDown = (ids: readonly string[]) => {
      for (const key of pressed) key.dataset.down = "false";
      const keyboard = keyboardRef.current;
      pressed = keyboard
        ? ids.flatMap((id) => {
            const key = keyboard.querySelector<HTMLElement>(`[data-key="${CSS.escape(id)}"]`);
            return key ? [key] : [];
          })
        : [];
      for (const key of pressed) key.dataset.down = "true";
    };

    const stop = loopWhileVisible(screenRef.current, async (wait) => {
      // Reset (behind the fade that ended the previous loop).
      setTyped(0);
      setDown([]);
      setGrammar(false);
      setMood("idle");
      look(NEUTRAL);
      await wait(60);
      setFading(false);

      // Scene 1: the screen wakes; the mascot turns to the editor.
      setAwake(true);
      await wait(900);
      setMood("watching");
      look(gazeAt(caretRef.current));
      await wait(700);

      // Scenes 2–4: type the essay — key press and character in the same step.
      const startedAt = Date.now();
      let planned = 0; // ms of the schedule used so far
      for (let i = 1; i <= DEMO_TEXT.length; i += 1) {
        // A slow device falls behind its timers; then one step types up to three characters
        // (never across a paragraph break), so the visible pace stays the same on every device.
        for (
          let extra = 0;
          extra < 2 &&
          Date.now() - startedAt > planned + 80 &&
          i < DEMO_TEXT.length &&
          DEMO_TEXT[i - 1] !== "\n" &&
          DEMO_TEXT[i] !== "\n";
          extra += 1
        ) {
          planned += STEP_MS + gapAfter(DEMO_TEXT[i - 1] ?? "", i);
          i += 1;
        }
        const ch = DEMO_TEXT[i - 1] ?? "";
        if (ch === "\n") {
          // End of a paragraph: pause and look over the finished text, then Return.
          setMood("pause");
          look(gazeAt(firstParaRef.current, 0.45, 0.5));
          setGrammar(true);
          await wait(1300);
          setMood("watching");
          setDown(keysFor(ch));
          setTyped(i);
          await wait(16);
          look(gazeAt(caretRef.current));
          await wait(150);
          setDown([]);
          await wait(450);
          planned += 1300 + 16 + 150 + 450;
          continue;
        }
        // One update per character: the previous key is released as the next one goes down.
        setDown(keysFor(ch));
        setTyped(i);
        if (i % 3 === 0) {
          // The mascot follows the caret (every few characters keeps the work per key low).
          await wait(16);
          look(gazeAt(caretRef.current));
          await wait(STEP_MS - 16);
        } else {
          await wait(STEP_MS);
        }
        if (ch === "." || ch === ",") setDown([]); // a short rest after punctuation
        await wait(gapAfter(ch, i));
        planned += STEP_MS + gapAfter(ch, i);
      }
      setDown([]);

      // Scene 5: complete. The mascot nods and gives a thumbs-up; hold, fade, replay.
      await wait(500);
      setMood("done");
      look({ fx: 0.5, fy: 0.55 });
      await wait(3600);
      setMood("idle");
      look(NEUTRAL);
      setFading(true);
      await wait(700);
    });
    return () => {
      stop();
      setDown([]);
    };
  }, [finished]);

  const shownTyped = finished ? DEMO_TEXT.length : typed;
  const text = DEMO_TEXT.slice(0, shownTyped);
  const words = countWords(text);
  const firstDone = shownTyped > FIRST_LENGTH;
  const allDone = shownTyped >= DEMO_TEXT.length;

  return (
    <div
      className="wx-demo"
      data-awake={finished || awake}
      data-fading={!finished && fading}
      data-static={finished}
    >
      <TiltScene className="wx-scene">
        <div className="wx-rig">
          <div className="wx-device">
            <div className="wx-lid">
              <div className="wx-camera" />
              <div ref={screenRef} className="wx-screen">
                <div className="wx-app">
                  <WritingApp
                    paragraphs={text.split("\n")}
                    words={words}
                    firstDone={firstDone}
                    allDone={allDone}
                    caretRef={caretRef}
                    firstParaRef={firstParaRef}
                    caretBlink={finished || mood === "pause" || mood === "idle"}
                    caretOn={finished || !allDone}
                  />
                </div>
              </div>
              <Mascot botRef={botRef} mood={finished ? "done" : mood} still={finished} />
            </div>
            <div className="wx-base">
              <div className="wx-floor" />
              {[1, 2, 3, 4, 5, 6, 7, 8].map((layer) => (
                <div key={layer} className="wx-rim" style={{ "--layer": layer } as CSSProperties} />
              ))}
              <div className="wx-deck">
                <div className="wx-hinge" />
                <Keyboard keyboardRef={keyboardRef} />
                <div className="wx-trackpad" />
              </div>
            </div>
          </div>
        </div>
      </TiltScene>

      {/* Outside the 3D scene, so the laptop's base can never cut through them. */}
      <div className="wx-floaters">
        <Floaters
          words={words}
          firstDone={firstDone}
          allDone={allDone}
          grammar={finished || grammar}
        />
      </div>
    </div>
  );
}

function WritingApp({
  paragraphs,
  words,
  firstDone,
  allDone,
  caretRef,
  firstParaRef,
  caretOn,
  caretBlink,
}: {
  paragraphs: string[];
  words: number;
  firstDone: boolean;
  allDone: boolean;
  caretRef: RefObject<HTMLSpanElement | null>;
  firstParaRef: RefObject<HTMLParagraphElement | null>;
  caretOn: boolean;
  caretBlink: boolean;
}) {
  const progress = Math.min(100, (words / TARGET_WORDS) * 100);
  const planState = (i: number) => {
    if (i === 0) return firstDone ? "done" : "now";
    if (i === 1) return allDone ? "done" : firstDone ? "now" : "next";
    return "next";
  };
  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <div className="wx-topbar flex items-center gap-[1.2em] border-b bg-card px-[1.4em] py-[0.7em]">
        <span className="flex items-center gap-[0.5em] text-sm font-bold tracking-tight">
          <span className="grid size-[1.8em] place-items-center rounded-[0.45em] bg-primary text-primary-foreground">
            <GraduationCapIcon className="size-[1.05em]" />
          </span>
          IELTS <span className="-ml-[0.3em] text-primary">MASTER</span>
        </span>
        <span className="wx-wide-only text-xs text-muted-foreground">
          Writing practice
          <span className="ml-[0.5em] rounded-full bg-muted px-[0.55em] py-px font-medium">
            Sample
          </span>
        </span>
        <span className="ml-auto flex items-center gap-[0.35em] rounded-full bg-muted px-[0.8em] py-[0.25em] text-xs font-semibold tabular-nums">
          <Clock3Icon className="size-[1em] text-primary" />
          36:20
        </span>
      </div>

      <div className="wx-app-body min-h-0 flex-1">
        <aside className="wx-task flex flex-col gap-[0.9em] border-r bg-surface p-[1.3em]">
          <span className="w-fit rounded-[0.4em] bg-primary px-[0.6em] py-[0.2em] text-xs font-bold text-primary-foreground">
            Writing Task 2
          </span>
          <p className="text-sm leading-relaxed font-semibold">
            In many countries, more people now work from home than ever before. Do the advantages of
            this development outweigh the disadvantages?
          </p>
          <p className="text-xs text-muted-foreground">Write at least 250 words.</p>
          <div className="mt-auto space-y-[0.4em]">
            <span className="text-xs font-semibold text-muted-foreground">Your plan</span>
            {PLAN.map((step, i) => {
              const state = planState(i);
              return (
                <div
                  key={step}
                  className={cn(
                    "wx-fade flex items-center gap-[0.5em] rounded-[0.45em] px-[0.6em] py-[0.3em] text-xs",
                    state === "now" && "bg-accent font-semibold text-accent-foreground",
                    state === "next" && "text-muted-foreground",
                  )}
                >
                  <span
                    className={cn(
                      "wx-fade grid size-[1.25em] shrink-0 place-items-center rounded-full border",
                      state === "done" && "border-success bg-success text-background",
                      state === "now" && "border-primary",
                    )}
                  >
                    {state === "done" && <CheckIcon className="size-[0.8em]" />}
                  </span>
                  {step}
                </div>
              );
            })}
          </div>
        </aside>

        <section className="flex min-h-0 flex-col gap-[0.75em] p-[1.4em] pb-[1em]">
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              <span className="wx-narrow-only mr-[0.5em] rounded-[0.35em] bg-primary px-[0.5em] py-px font-bold text-primary-foreground">
                Task 2
              </span>
              Essay · Draft 1
            </span>
            <span className="flex items-center gap-[0.3em]">
              <CheckIcon className="size-[1em] text-success" /> Autosaved
            </span>
          </div>
          <h4 className="font-heading text-lg leading-snug font-bold">
            Remote work: a change for the better?
          </h4>
          <div className="wx-editor flex-1 space-y-[0.75em] text-base leading-[1.7]">
            {paragraphs.map((para, i) => (
              <p key={i} ref={i === 0 ? firstParaRef : undefined}>
                {para}
                {i === paragraphs.length - 1 && (
                  <span
                    ref={caretRef}
                    className="wx-caret"
                    data-on={caretOn}
                    data-blink={caretBlink}
                  />
                )}
              </p>
            ))}
          </div>
          <div className="flex items-center gap-[0.9em] border-t pt-[0.75em] text-xs">
            <span className="wx-count font-semibold tabular-nums">{words} words</span>
            <span className="h-[0.45em] flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="wx-progress block h-full rounded-full"
                style={{ width: `${progress}%` }}
              />
            </span>
            <span className="text-muted-foreground tabular-nums">Aim: {TARGET_WORDS}+</span>
          </div>
        </section>
      </div>
    </div>
  );
}

/** The keyboard renders once; the demo presses keys by toggling `data-down` on them. */
const Keyboard = memo(function Keyboard({
  keyboardRef,
}: {
  keyboardRef: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div ref={keyboardRef} className="wx-keyboard">
      {KEYBOARD.map((row, r) => (
        <div key={r} className={cn("wx-row", r === 0 && "wx-row-fn")}>
          {row.map(([id, label, grow = 1]) => (
            <span
              key={id}
              className="wx-key"
              data-key={id}
              data-down="false"
              data-mod={grow > 1.2 || label.length > 2}
              style={{ flexGrow: grow }}
            >
              {label}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
});

/** The AI mascot seated on the top-right corner of the lid; its gaze is set via --fx / --fy. */
function Mascot({
  botRef,
  mood,
  still,
}: {
  botRef: RefObject<HTMLDivElement | null>;
  mood: Mood;
  still: boolean;
}) {
  const gaze = still ? { fx: 0.5, fy: 0.55 } : NEUTRAL;
  return (
    <div
      ref={botRef}
      className="wx-bot"
      data-mood={mood}
      style={{ "--fx": gaze.fx, "--fy": gaze.fy } as CSSProperties}
    >
      <span className="wx-bot-contact" />
      <span className="wx-bot-leg wx-bot-leg-l" />
      <span className="wx-bot-leg wx-bot-leg-r" />
      <span className="wx-bot-arm wx-bot-arm-l">
        <span className="wx-bot-hand" />
      </span>
      <span className="wx-bot-body">
        <span className="wx-bot-chest" />
      </span>
      <span className="wx-bot-arm wx-bot-arm-r">
        <span className="wx-bot-hand" />
      </span>
      <span className="wx-bot-nod">
        <span className="wx-bot-head">
          <span className="wx-bot-antenna" />
          <span className="wx-bot-ear wx-bot-ear-l" />
          <span className="wx-bot-ear wx-bot-ear-r" />
          <span className="wx-bot-face">
            <span className="wx-bot-eyes">
              <span className="wx-bot-eye" />
              <span className="wx-bot-eye" />
            </span>
          </span>
        </span>
      </span>
    </div>
  );
}

function SampleTag() {
  return (
    <span className="rounded-full bg-muted px-1.5 py-px text-[0.625rem] font-medium text-muted-foreground">
      Sample
    </span>
  );
}

function Floaters({
  words,
  firstDone,
  allDone,
  grammar,
}: {
  words: number;
  firstDone: boolean;
  allDone: boolean;
  grammar: boolean;
}) {
  const paragraphsDone = (firstDone ? 1 : 0) + (allDone ? 1 : 0);
  const vocabBars = Math.ceil((words / DEMO_WORDS) * 7);
  return (
    <>
      <div className="wx-float wx-float-words">
        <div className="wx-chip">
          <span
            className="wx-ring"
            style={{ "--p": `${Math.min(100, (words / TARGET_WORDS) * 100)}%` } as CSSProperties}
          >
            <span className="wx-ring-value tabular-nums">{words}</span>
          </span>
          <span>
            <span className="block text-sm font-semibold">Word count</span>
            <span className="block text-xs text-muted-foreground">Aim: 250+ words</span>
          </span>
        </div>
      </div>

      <div className="wx-float wx-float-vocab">
        <div className="wx-chip">
          <span className="wx-chip-icon">
            <BookAIcon className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center justify-between gap-2 text-sm font-semibold">
              Vocabulary
              <SampleTag />
            </span>
            <span className="mt-1.5 flex h-5 items-end gap-1">
              {[40, 65, 50, 80, 60, 90, 70].map((h, i) => (
                <span
                  key={i}
                  className="wx-vbar"
                  data-on={i < vocabBars}
                  style={{ height: `${h}%` }}
                />
              ))}
            </span>
          </span>
        </div>
      </div>

      <div className="wx-float wx-float-grammar" data-show={grammar}>
        <div className="wx-chip">
          <span className="wx-chip-icon wx-chip-icon-ok">
            <SpellCheck2Icon className="size-4" />
          </span>
          <span>
            <span className="flex items-center gap-2 text-sm font-semibold">
              Grammar
              <SampleTag />
            </span>
            <span className="block text-xs text-muted-foreground">
              {grammar ? "Paragraph 1: no issues found" : "Checked after each paragraph"}
            </span>
          </span>
        </div>
      </div>

      <div className="wx-float wx-float-progress">
        <div className="wx-chip">
          <span className="wx-chip-icon">
            <TrendingUpIcon className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-semibold">Writing progress</span>
            <span className="mt-1.5 grid grid-cols-4 gap-1">
              {PLAN.map((step, i) => (
                <span key={step} className="wx-pseg" data-on={i < paragraphsDone} />
              ))}
            </span>
            <span className="mt-1 block text-xs text-muted-foreground tabular-nums">
              {paragraphsDone} of {PLAN.length} paragraphs
            </span>
          </span>
        </div>
      </div>
    </>
  );
}
