"use client";

import { CheckIcon, Clock3Icon, GraduationCapIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { loopWhileVisible, useReducedMotion } from "@/components/marketing/demo-motion";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { cn } from "@/lib/utils";

/* Original sample Reading passage and questions. */
type Question =
  | { n: number; kind: "tfng"; text: string; answer: "TRUE" | "FALSE" | "NOT GIVEN" }
  | { n: number; kind: "gap"; before: string; after: string; answer: string };

export const QUESTIONS: readonly Question[] = [
  {
    n: 14,
    kind: "tfng",
    text: "A rooftop garden can keep the floors below it cooler in summer.",
    answer: "TRUE",
  },
  {
    n: 15,
    kind: "tfng",
    text: "Most cities now require new buildings to include a rooftop garden.",
    answer: "NOT GIVEN",
  },
  {
    n: 16,
    kind: "gap",
    before: "Stored rainwater is later used to water",
    after: ".",
    answer: "vegetable beds",
  },
];
const FIRST = QUESTIONS[0]?.n ?? 14;
const TOTAL = 40;
const START_SECONDS = 42 * 60 + 18;
const OPTIONS = ["TRUE", "FALSE", "NOT GIVEN"] as const;

type State = { current: number; answered: number; picked: string | null; typed: number };
const START: State = { current: 0, answered: FIRST - 1, picked: null, typed: 0 };
const FINISHED: State = {
  current: QUESTIONS.length - 1,
  answered: FIRST - 1 + QUESTIONS.length,
  picked: null,
  typed: QUESTIONS.at(-1)?.answer.length ?? 0,
};

/**
 * The mock exam workspace with a looping demonstration: the timer counts down, question by
 * question an answer is chosen (or typed, for the gap fill), the question map and progress
 * update, then it starts over. Illustrative only. Runs while on screen; reduced motion shows a
 * static state. Decorative: rendered inside an aria-hidden, inert container.
 */
export function MockExamDemo() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<State>(START);
  const [seconds, setSeconds] = useState(START_SECONDS);
  const finished = useReducedMotion();

  useEffect(() => {
    if (finished) return;
    const id = window.setInterval(() => setSeconds((s) => (s > 0 ? s - 1 : START_SECONDS)), 1000);
    return () => window.clearInterval(id);
  }, [finished]);

  useEffect(() => {
    if (finished) return;
    return loopWhileVisible(rootRef.current, async (wait) => {
      setState(START);
      await wait(900);
      for (let q = 0; q < QUESTIONS.length; q += 1) {
        const question = QUESTIONS[q];
        if (!question) continue;
        setState((s) => ({ ...s, current: q, picked: null, typed: 0 }));
        await wait(1300); // read the question
        if (question.kind === "tfng") {
          setState((s) => ({ ...s, picked: question.answer }));
        } else {
          for (let c = 1; c <= question.answer.length; c += 1) {
            setState((s) => ({ ...s, typed: c }));
            await wait(question.answer[c - 1] === " " ? 140 : 90);
          }
        }
        await wait(500);
        setState((s) => ({ ...s, answered: FIRST + q }));
        await wait(900);
      }
      await wait(2400);
    });
  }, [finished]);

  const s = finished ? FINISHED : state;
  const time = finished ? START_SECONDS : seconds;
  const clock = `${String(Math.floor(time / 60)).padStart(2, "0")}:${String(time % 60).padStart(2, "0")}`;
  const answeredCount = s.answered;
  const progress = answeredCount / TOTAL;

  return (
    <div ref={rootRef} className="mk-demo" data-static={finished}>
      <TiltScene className="mk-scene">
        <div className="mk-window">
          {/* Exam top bar */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-3">
            <span className="flex items-center gap-2 text-sm font-bold tracking-tight">
              <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground">
                <GraduationCapIcon className="size-4" />
              </span>
              IELTS <span className="-ml-1 text-primary">MASTER</span>
              <span className="ml-1 rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground">
                Mock exam · Sample
              </span>
            </span>
            <span className="mk-tabs">
              {["Listening", "Reading", "Writing"].map((tab, i) => (
                <span key={tab} data-state={i === 0 ? "done" : i === 1 ? "now" : "next"}>
                  {i === 0 && <CheckIcon className="size-3.5" />}
                  {tab}
                </span>
              ))}
            </span>
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-sm font-semibold tabular-nums">
              <Clock3Icon className="size-4 text-primary" />
              {clock}
            </span>
          </div>
          <div className="flex items-center gap-3 border-b bg-surface px-4 py-2 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground">Reading · Passage 2</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="mk-bar block h-full rounded-full"
                style={{ width: `${progress * 100}%` }}
              />
            </span>
            <span className="tabular-nums">
              {answeredCount} / {TOTAL} answered
            </span>
          </div>

          <div className="mk-body">
            <article className="mk-passage">
              <h4 className="font-heading text-base font-bold text-foreground">
                The Return of the Rooftop Garden
              </h4>
              <p>
                <b>A</b> Across many cities, flat roofs that once held only air-conditioning units
                are being turned into gardens. Studies of these projects suggest that a layer of
                soil and plants can keep the floors beneath noticeably cooler in summer.
              </p>
              <p>
                <b>B</b> Many of the gardens also collect rainwater, which is stored in tanks and
                later used to water vegetable beds. Supporters argue that such schemes make better
                use of space that would otherwise be wasted.
              </p>
            </article>

            <section className="mk-questions">
              <span className="text-xs font-semibold text-muted-foreground">
                Questions 14–16 · TRUE / FALSE / NOT GIVEN, then sentence completion
              </span>
              {QUESTIONS.map((q, i) => (
                <div key={q.n} className="mk-q" data-active={i === s.current}>
                  <span className="mk-qn">{q.n}</span>
                  {q.kind === "tfng" ? (
                    <div className="min-w-0 flex-1">
                      <p>{q.text}</p>
                      <span className="mt-2 flex flex-wrap gap-1.5">
                        {OPTIONS.map((opt) => {
                          const chosen =
                            (i === s.current && s.picked === opt) ||
                            (FIRST + i <= s.answered && q.answer === opt);
                          return (
                            <span key={opt} className="mk-opt" data-chosen={chosen}>
                              {opt}
                            </span>
                          );
                        })}
                      </span>
                    </div>
                  ) : (
                    <p className="min-w-0 flex-1 leading-[2.2]">
                      {q.before}{" "}
                      <span className="mk-gap" data-active={i === s.current}>
                        {i === s.current || FIRST + i <= s.answered
                          ? q.answer.slice(0, i === s.current ? s.typed : q.answer.length)
                          : ""}
                        {i === s.current && <span className="mk-caret" />}
                      </span>
                      {q.after}
                    </p>
                  )}
                </div>
              ))}
            </section>
          </div>

          {/* Question navigator */}
          <div className="mk-nav">
            {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
              <span
                key={n}
                data-state={
                  n === FIRST + s.current ? "current" : n <= s.answered ? "answered" : "open"
                }
              >
                {n}
              </span>
            ))}
            <span className="mk-nav-more">… 40</span>
          </div>
        </div>

        {/* Floating 3D elements */}
        <div className="mk-float mk-float-timer">
          <span
            className="mk-ring"
            style={{ "--p": `${(time / (60 * 60)) * 100}%` } as CSSProperties}
          >
            <Clock3Icon className="size-4" />
          </span>
          <span>
            <span className="block text-xs text-muted-foreground">Time left</span>
            <span className="block text-lg font-bold tabular-nums">{clock}</span>
          </span>
        </div>
        <div className="mk-float mk-float-progress">
          <span className="text-xs font-semibold">Exam progress</span>
          <span className="mt-2 grid grid-cols-4 gap-1">
            {["L", "R", "W", "S"].map((part, i) => (
              <span key={part} className={cn("mk-step", i === 0 && "is-done", i === 1 && "is-now")}>
                {part}
              </span>
            ))}
          </span>
          <span className="mt-1.5 block text-[0.6875rem] text-muted-foreground">
            Section 2 of 4 · Reading
          </span>
        </div>
        <div className="mk-pencil" aria-hidden="true">
          <span className="mk-pencil-tip" />
          <span className="mk-pencil-body" />
          <span className="mk-pencil-band" />
          <span className="mk-pencil-eraser" />
        </div>
      </TiltScene>
    </div>
  );
}
