"use client";

import { BookOpenTextIcon, CheckIcon, Clock3Icon } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";

import { cn } from "@/lib/utils";

/** The phrase selected in the passage and the answer typed into question 19. */
export const DEMO_PHRASE = "artificial light";
export const DEMO_ANSWER = "artificial light";

type CursorState = {
  x: number;
  y: number;
  ms: number;
  visible: boolean;
  pressed: boolean;
  ibeam: boolean;
  clicks: number;
};

const HIDDEN_CURSOR: CursorState = {
  x: 0,
  y: 0,
  ms: 0,
  visible: false,
  pressed: false,
  ibeam: false,
  clicks: 0,
};

/** Position of `el` in the layout coordinates of `root` (unaffected by 3D transforms). */
function localPoint(el: HTMLElement, root: HTMLElement, fx = 0, fy = 0.5) {
  let x = 0;
  let y = 0;
  let node: HTMLElement | null = el;
  while (node && node !== root) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent as HTMLElement | null;
  }
  return { x: x + el.offsetWidth * fx, y: y + el.offsetHeight * fy };
}

class Cancelled extends Error {}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True when the user asks for reduced motion (server render: false). */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

/**
 * The Reading app shown on the showcase display, with a looping demonstration:
 * cursor → select a phrase in the passage → move to the answer field → type the answer →
 * saved → reset. Runs only while on screen; with prefers-reduced-motion the finished state is
 * shown without any movement. Decorative: rendered inside an aria-hidden, inert container.
 */
export function ReadingDemo() {
  const screenRef = useRef<HTMLDivElement>(null);
  const phraseRef = useRef<HTMLSpanElement>(null);
  const selEndRef = useRef<HTMLSpanElement>(null);
  const fieldRef = useRef<HTMLSpanElement>(null);
  const restRef = useRef<HTMLSpanElement>(null);

  const [selected, setSelected] = useState(0);
  const [highlighted, setHighlighted] = useState(false);
  const [focused, setFocused] = useState(false);
  const [typed, setTyped] = useState(0);
  const [saved, setSaved] = useState(false);
  const [cursor, setCursor] = useState<CursorState>(HIDDEN_CURSOR);
  const finished = useReducedMotion(); // reduced motion: static completed state, no cursor

  useEffect(() => {
    if (finished) return;
    let cancelled = false;
    let onScreen = typeof IntersectionObserver === "undefined";
    let wake: (() => void) | null = null;
    const timers = new Set<number>();

    const wait = (ms: number) =>
      new Promise<void>((resolve, reject) => {
        const id = window.setTimeout(() => {
          timers.delete(id);
          if (cancelled) reject(new Cancelled());
          else resolve();
        }, ms);
        timers.add(id);
      });
    const whenOnScreen = () =>
      onScreen
        ? Promise.resolve()
        : new Promise<void>((resolve) => {
            wake = resolve;
          });
    const point = (el: HTMLElement | null, fx?: number, fy?: number) => {
      const root = screenRef.current;
      if (!el || !root) throw new Cancelled();
      return localPoint(el, root, fx, fy);
    };
    const moveTo = (p: { x: number; y: number }, ms: number, extra: Partial<CursorState> = {}) =>
      setCursor((c) => ({ ...c, x: p.x, y: p.y, ms, ...extra }));

    async function runOnce() {
      setSelected(0);
      setHighlighted(false);
      setFocused(false);
      setTyped(0);
      setSaved(false);
      const rest = point(restRef.current);
      setCursor({ ...HIDDEN_CURSOR, x: rest.x, y: rest.y });
      await wait(400);

      // Scene 1: the cursor appears and moves to the phrase.
      setCursor((c) => ({ ...c, visible: true, ms: 0 }));
      await wait(450);
      moveTo(point(phraseRef.current, 0, 0.55), 1100);
      await wait(1150);

      // Scene 2: press and drag to select the phrase, letter by letter.
      setCursor((c) => ({ ...c, ibeam: true, pressed: true, ms: 120 }));
      await wait(260);
      for (let i = 1; i <= DEMO_PHRASE.length; i += 1) {
        setSelected(i);
        await wait(16);
        moveTo(point(selEndRef.current, 0, 0.55), 50);
        await wait(46);
      }
      setCursor((c) => ({ ...c, pressed: false }));
      await wait(750);

      // Scene 3: move to the answer field and click into it.
      setCursor((c) => ({ ...c, ibeam: false }));
      moveTo(point(fieldRef.current, 0.1, 0.5), 1150);
      await wait(1200);
      setCursor((c) => ({ ...c, ibeam: true, pressed: true, clicks: c.clicks + 1, ms: 100 }));
      await wait(130);
      setSelected(0);
      setHighlighted(true); // the selection is kept as a highlight in the passage
      setFocused(true);
      setCursor((c) => ({ ...c, pressed: false }));
      await wait(250);
      // Move the pointer just below the field so the typing stays visible.
      const below = point(fieldRef.current, 0.25, 1);
      moveTo({ x: below.x, y: below.y + 18 }, 350, { ibeam: false });
      await wait(400);

      // Scene 4: type the answer character by character.
      for (let i = 1; i <= DEMO_ANSWER.length; i += 1) {
        setTyped(i);
        await wait(DEMO_ANSWER[i - 1] === " " ? 170 : 85 + ((i * 37) % 45));
      }

      // Scene 5: saved; the cursor drifts away, then everything resets.
      await wait(450);
      setSaved(true);
      setFocused(false);
      const field = point(fieldRef.current, 1, 1);
      moveTo({ x: field.x + 40, y: field.y + 40 }, 900, { ibeam: false });
      await wait(2800);
      setCursor((c) => ({ ...c, visible: false, ms: 0 }));
      await wait(450);
    }

    const observer =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(
            ([entry]) => {
              onScreen = entry?.isIntersecting ?? false;
              if (onScreen && wake) {
                wake();
                wake = null;
              }
            },
            { threshold: 0.25 },
          );
    if (observer && screenRef.current) observer.observe(screenRef.current);

    (async () => {
      while (!cancelled) {
        await whenOnScreen();
        await runOnce();
      }
    })().catch(() => undefined);

    return () => {
      cancelled = true;
      for (const id of timers) window.clearTimeout(id);
      observer?.disconnect();
    };
  }, [finished]);

  const shownSelected = finished ? 0 : selected;
  const shownHighlight = finished || highlighted;
  const shownTyped = finished ? DEMO_ANSWER.length : typed;
  const shownSaved = finished || saved;

  return (
    <div ref={screenRef} className="rx-app relative bg-background text-foreground">
      <TopBar answered={shownSaved ? 19 : 18} />
      <div className="rx-body">
        <article className="space-y-[0.9em] border-b p-[1.6em] text-sm leading-[1.65] text-muted-foreground @[40rem]:border-r @[40rem]:border-b-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold tracking-[0.12em] text-primary uppercase">
              Reading passage 2
            </span>
            <span className="text-xs">Paragraphs A–D</span>
          </div>
          <h4 className="font-heading text-lg leading-snug font-bold text-foreground">
            Why Cities Are Turning Down the Lights
          </h4>
          <Para label="A" className="rx-wide-only">
            For most of human history, the night sky was dark enough to reveal thousands of stars.
            Today, more than half of the world&apos;s population lives where the glow of street
            lamps, offices and advertising hides all but the brightest of them.
          </Para>
          <Para label="B">
            The effects reach far beyond astronomy. Ecologists have shown that many migrating birds
            become confused by{" "}
            <span ref={phraseRef} className="relative">
              <span className={cn(shownHighlight && "rx-highlight", "text-foreground")}>
                {shownSelected > 0 ? (
                  <>
                    <span className="rx-selection">{DEMO_PHRASE.slice(0, shownSelected)}</span>
                    <span ref={selEndRef} />
                    {DEMO_PHRASE.slice(shownSelected)}
                  </>
                ) : (
                  <>
                    <span ref={selEndRef} />
                    {DEMO_PHRASE}
                  </>
                )}
              </span>
            </span>
            , circling illuminated buildings until they are exhausted. Some insects are drawn to
            lamps in such numbers that local populations decline.
          </Para>
          <Para label="C">
            In response, a growing number of cities have introduced lighting plans. Lamps are fitted
            with shields that direct light downwards, and warmer colours replace the harsh
            blue-white glare that travels furthest through the atmosphere.
            <span ref={restRef} className="ml-[0.4em] inline-block" />
          </Para>
          <Para label="D" className="rx-wide-only">
            Early results are encouraging. Where such measures have been adopted, residents report
            seeing the Milky Way again, while spending on public lighting has fallen noticeably.
          </Para>
        </article>
        <section className="flex flex-col gap-[0.9em] bg-surface p-[1.6em]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">Questions 18–21</span>
            <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground">
              Sentence completion
            </span>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Complete the sentences below. Choose{" "}
            <span className="font-semibold text-foreground">NO MORE THAN TWO WORDS</span> from the
            passage for each answer.
          </p>
          <QuestionRow number={18} before="Light pollution hides all but the brightest" after=".">
            <AnswerBox value="stars" done />
          </QuestionRow>
          <QuestionRow
            number={19}
            before="Many migrating birds become confused by"
            after="."
            active
          >
            <span
              ref={fieldRef}
              className="rx-field relative inline-flex h-[2.1em] min-w-[10.5em] items-center rounded-[0.5em] border bg-card px-[0.65em] align-middle font-medium text-foreground"
              data-focused={focused && !shownSaved}
              data-saved={shownSaved}
            >
              {DEMO_ANSWER.slice(0, shownTyped)}
              {focused && !shownSaved && <span className="rx-caret" />}
              {shownSaved && <CheckIcon className="ml-auto size-[1.1em] pl-[0.3em] text-success" />}
            </span>
          </QuestionRow>
          <QuestionRow number={20} before="Lamp shields direct light" after=".">
            <AnswerBox value="" />
          </QuestionRow>
          <QuestionRow number={21} before="Warmer colours replace the blue-white" after=".">
            <AnswerBox value="" />
          </QuestionRow>
          <div className="mt-auto flex items-center justify-between gap-3 border-t pt-[0.9em]">
            <span
              className={cn(
                "rx-fade inline-flex items-center gap-1.5 text-xs font-medium text-success",
                shownSaved ? "opacity-100" : "opacity-0",
              )}
            >
              <CheckIcon className="size-[1em]" /> Answer saved
            </span>
            <span className="flex items-center gap-2">
              <span className="rounded-[0.45em] border px-2.5 py-1 text-xs text-muted-foreground">
                ← Previous
              </span>
              <span className="rounded-[0.45em] bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground">
                Next →
              </span>
            </span>
          </div>
        </section>
      </div>
      <BottomNav answered={shownSaved ? 19 : 18} />
      <span
        aria-hidden="true"
        className="rx-cursor"
        data-pressed={cursor.pressed}
        data-ibeam={cursor.ibeam}
        style={
          {
            transform: `translate3d(${cursor.x}px, ${cursor.y}px, 0)`,
            transitionDuration: `${cursor.ms}ms, 300ms`,
            opacity: cursor.visible && !finished ? 1 : 0,
          } as CSSProperties
        }
      >
        {cursor.clicks > 0 && <span key={cursor.clicks} className="rx-click" />}
        {cursor.ibeam ? <IBeam /> : <Arrow />}
      </span>
    </div>
  );
}

function Para({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p className={className}>
      <span className="mr-[0.6em] inline-grid size-[1.5em] place-items-center rounded-[0.35em] bg-muted text-xs font-bold text-foreground">
        {label}
      </span>
      {children}
    </p>
  );
}

function QuestionRow({
  number,
  before,
  after,
  active,
  children,
}: {
  number: number;
  before: string;
  after: string;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-[0.6em] border bg-card p-[0.8em] text-sm leading-[2.1]",
        active && "border-primary/40 shadow-elevation-1",
      )}
    >
      <span className="mr-[0.5em] font-bold text-primary tabular-nums">{number}</span>
      {before} {children}
      {after}
    </div>
  );
}

function AnswerBox({ value, done }: { value: string; done?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-[2.1em] min-w-[8em] items-center rounded-[0.5em] border px-[0.65em] align-middle font-medium",
        done ? "border-primary/30 bg-primary/5" : "border-dashed bg-card text-muted-foreground",
      )}
    >
      {value}
    </span>
  );
}

function TopBar({ answered }: { answered: number }) {
  return (
    <div className="flex flex-wrap items-center gap-x-[1.4em] gap-y-[0.6em] border-b bg-card px-[1.6em] py-[0.8em]">
      <span className="flex items-center gap-2 text-sm font-bold tracking-tight">
        <span className="grid size-[1.8em] place-items-center rounded-[0.45em] bg-primary text-primary-foreground">
          <BookOpenTextIcon className="size-[1em]" />
        </span>
        IELTS <span className="-ml-1.5 text-primary">MASTER</span>
      </span>
      <span className="text-xs text-muted-foreground">
        Academic Reading · Practice test
        <span className="ml-1.5 rounded-full bg-muted px-1.5 py-px font-medium">Sample</span>
      </span>
      <span className="flex items-center gap-1 text-xs font-medium">
        {["Passage 1", "Passage 2", "Passage 3"].map((name, i) => (
          <span
            key={name}
            className={cn(
              "rounded-[0.45em] px-2.5 py-1",
              i === 1 ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
            )}
          >
            {i === 0 && "✓ "}
            {name}
          </span>
        ))}
      </span>
      <span className="ml-auto flex items-center gap-2 text-xs font-semibold tabular-nums">
        <span className="rounded-full bg-muted px-2.5 py-1">{answered} / 40 answered</span>
        <span className="flex items-center gap-1 rounded-full bg-muted px-2.5 py-1">
          <Clock3Icon className="size-[1em] text-primary" />
          38:12
        </span>
      </span>
    </div>
  );
}

function BottomNav({ answered }: { answered: number }) {
  return (
    <div className="flex flex-wrap items-center gap-[0.35em] border-t bg-card px-[1.6em] py-[0.7em] text-xs">
      <span className="mr-[0.6em] font-semibold text-muted-foreground">Passage 2</span>
      {Array.from({ length: 13 }, (_, i) => i + 14).map((n) => (
        <span
          key={n}
          className={cn(
            "rx-fade grid h-[1.9em] w-[2.2em] place-items-center rounded-[0.4em] font-semibold tabular-nums",
            n <= answered ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
            n === 19 && n > answered && "ring-1 ring-primary",
          )}
        >
          {n}
        </span>
      ))}
    </div>
  );
}

function Arrow() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M4 2.5 19.5 13.2l-7 .9 4.2 7.6-2.9 1.5-4.2-7.7-5.6 4.9Z"
        fill="white"
        stroke="#0f172a"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IBeam() {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      <path
        d="M9 3h2.2c.5 0 .8.2.8.6.1-.4.4-.6.8-.6H15M9 21h2.2c.5 0 .8-.2.8-.6.1.4.4.6.8.6H15M12 3.6v16.8"
        stroke="white"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      <path
        d="M9 3h2.2c.5 0 .8.2.8.6.1-.4.4-.6.8-.6H15M9 21h2.2c.5 0 .8-.2.8-.6.1.4.4.6.8.6H15M12 3.6v16.8"
        stroke="#0f172a"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
