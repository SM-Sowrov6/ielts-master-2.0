"use client";

import { BookOpenTextIcon, LayoutListIcon, TextQuoteIcon, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

import { loopWhileVisible, useReducedMotion } from "@/components/marketing/demo-motion";
import { Icon3D, type Tone } from "@/components/marketing/skill-marquee";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { cn } from "@/lib/utils";

/* The sample coaching exchange. */
export const STUDENT_MESSAGE =
  "I'm struggling to improve my IELTS Writing Task 2 score. Can you help me?";
export const COACH_MESSAGE =
  "Of course! Let's work on your essay structure first. I noticed that developing clearer topic sentences could help improve your coherence and cohesion.";
const COACH_WORDS = COACH_MESSAGE.split(" ");

/** Qualitative, illustrative feedback: a sample, not an assessment. */
const FEEDBACK = [
  { name: "Task Response", status: "Needs improvement", level: 2, tone: "amber" },
  { name: "Coherence & Cohesion", status: "Good", level: 4, tone: "emerald" },
  { name: "Lexical Resource", status: "Good", level: 4, tone: "emerald" },
  { name: "Grammar", status: "Improving", level: 3, tone: "blue" },
] as const;

const RECOMMENDATIONS: readonly { title: string; meta: string; icon: LucideIcon; tone: Tone }[] = [
  {
    title: "Improve Essay Structure",
    meta: "Writing · Task 2",
    icon: LayoutListIcon,
    tone: "blue",
  },
  {
    title: "Practise Topic Sentences",
    meta: "Writing · 3 drills",
    icon: TextQuoteIcon,
    tone: "emerald",
  },
  { title: "Expand Academic Vocabulary", meta: "Vocabulary", icon: BookOpenTextIcon, tone: "teal" },
];

/** The robot's state: listening to the student, thinking, talking, or pleased (nod). */
type Mood = "idle" | "listening" | "thinking" | "talking" | "done";

type Scene = {
  student: boolean;
  typing: boolean;
  words: number;
  feedback: boolean;
  recs: number;
  mood: Mood;
};
const START: Scene = {
  student: false,
  typing: false,
  words: 0,
  feedback: false,
  recs: 0,
  mood: "idle",
};
const FINISHED: Scene = {
  student: true,
  typing: false,
  words: COACH_WORDS.length,
  feedback: true,
  recs: RECOMMENDATIONS.length,
  mood: "done",
};

/**
 * The AI Coach workspace with its looping demonstration, driven by one timeline: the student's
 * message arrives (the coach turns to it), the coach thinks (typing dots), answers word by word
 * while talking, the sample feedback card appears, the recommendations enter one by one, and the
 * coach nods; hold, fade the conversation and replay. Visual demonstration only. Runs while on
 * screen; with prefers-reduced-motion the finished state is shown without motion. Decorative:
 * rendered inside an aria-hidden, inert container.
 */
export function CoachDemo() {
  const rootRef = useRef<HTMLDivElement>(null);
  const [scene, setScene] = useState<Scene>(START);
  const [fading, setFading] = useState(false);
  const finished = useReducedMotion();

  useEffect(() => {
    if (finished) return;
    const update = (patch: Partial<Scene>) => setScene((s) => ({ ...s, ...patch }));
    return loopWhileVisible(rootRef.current, async (wait) => {
      setScene(START);
      await wait(60);
      setFading(false);
      await wait(900);

      update({ student: true, mood: "listening" }); // 3 · the student's message
      await wait(1300);
      update({ typing: true, mood: "thinking" });
      await wait(1200);
      update({ typing: false, mood: "talking" }); // 4 · the reply, word by word
      for (let w = 1; w <= COACH_WORDS.length; w += 1) {
        update({ words: w });
        const word = COACH_WORDS[w - 1] ?? "";
        await wait(/[.!?]$/.test(word) ? 420 : /,$/.test(word) ? 260 : 120);
      }
      update({ mood: "idle" });
      await wait(450);
      update({ feedback: true }); // 5 · sample feedback
      await wait(1000);
      for (let r = 1; r <= RECOMMENDATIONS.length; r += 1) {
        update({ recs: r }); // 6 · recommendations, staggered
        await wait(380);
      }
      await wait(300);
      update({ mood: "done" }); // 7 · a gentle nod
      await wait(3600);
      setFading(true); // 8 · back to the start
      await wait(800);
    });
  }, [finished]);

  const s = finished ? FINISHED : scene;

  return (
    <div
      ref={rootRef}
      className="cx-demo"
      data-mood={s.mood}
      data-fading={!finished && fading}
      data-static={finished}
    >
      <TiltScene className="cx-scene">
        <div className="cx-layout">
          <div className="cx-robot-col">
            <CoachRobot />
          </div>

          <div className="cx-window-wrap">
            <div className="cx-window">
              <div className="flex items-center gap-2.5 border-b px-4 py-3">
                <span className="cx-badge">
                  <MiniBot />
                </span>
                <span className="text-sm font-semibold">AI Coach</span>
                <span className="cx-online" />
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  Writing · Task 2 focus
                </span>
                <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground">
                  Sample
                </span>
              </div>

              <div className="cx-body">
                <div className="cx-chat">
                  {s.student && (
                    <div className="cx-msg" data-from="student">
                      <p className="cx-bubble">{STUDENT_MESSAGE}</p>
                      <span className="cx-time">You · 09:41</span>
                    </div>
                  )}
                  {s.typing && (
                    <div className="cx-msg" data-from="coach">
                      <span className="cx-badge cx-badge-sm">
                        <MiniBot />
                      </span>
                      <p className="cx-bubble cx-typing">
                        <i />
                        <i />
                        <i />
                      </p>
                    </div>
                  )}
                  {s.words > 0 && (
                    <div className="cx-msg" data-from="coach">
                      <span className="cx-badge cx-badge-sm">
                        <MiniBot />
                      </span>
                      <div className="min-w-0">
                        <p className="cx-bubble cx-coach-text">
                          {COACH_WORDS.slice(0, s.words).join(" ")}
                        </p>
                        <span className="cx-time">AI Coach · 09:41</span>
                      </div>
                    </div>
                  )}
                </div>

                <div className="cx-feedback" data-show={s.feedback}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[0.6875rem] font-bold tracking-[0.12em] text-primary uppercase">
                      Writing feedback
                    </span>
                    <span className="rounded-full bg-muted px-1.5 py-px text-[0.625rem] font-medium text-muted-foreground">
                      Sample
                    </span>
                  </div>
                  <ul className="mt-3 space-y-2.5">
                    {FEEDBACK.map((row, i) => (
                      <li key={row.name} className="text-xs">
                        <span className="flex items-baseline justify-between gap-2">
                          <span className="font-medium">{row.name}</span>
                          <span className="cx-status" data-tone={row.tone}>
                            {row.status}
                          </span>
                        </span>
                        <span className="mt-1.5 grid grid-cols-5 gap-[3px]">
                          {Array.from({ length: 5 }, (_, seg) => (
                            <span
                              key={seg}
                              className={cn("cx-seg", seg < row.level && "cx-seg-on")}
                              data-tone={row.tone}
                              style={{ "--d": `${i * 110 + seg * 60}ms` } as CSSProperties}
                            />
                          ))}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 border-t pt-2 text-[0.625rem] leading-snug text-muted-foreground">
                    Illustrative example, not a band score or an assessment.
                  </p>
                </div>
              </div>
            </div>

            <div className="cx-recs">
              {RECOMMENDATIONS.map((rec, i) => (
                <div key={rec.title} className="cx-rec" data-show={i < s.recs}>
                  <Icon3D icon={rec.icon} tone={rec.tone} delay={-i * 1.4} />
                  <span className="min-w-0">
                    <span className="block text-sm leading-tight font-semibold">{rec.title}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">{rec.meta}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </TiltScene>
    </div>
  );
}

/** A miniature of the coach's face, used as its avatar in the window and the chat. */
function MiniBot() {
  return (
    <span className="cx-minibot">
      <span className="cx-minibot-visor">
        <i />
        <i />
      </span>
    </span>
  );
}

/** The coach: the IELTS MASTER robot (white shell, glass visor, emerald eyes) with arms. */
function CoachRobot() {
  return (
    <div className="cx-robot">
      <span className="cx-shadow" />
      <span className="cx-glow" />
      <span className="cx-figure">
        <span className="cx-arm cx-arm-l">
          <span className="cx-hand" />
        </span>
        <span className="cx-torso">
          <span className="cx-collar" />
          <span className="cx-core" />
        </span>
        <span className="cx-arm cx-arm-r">
          <span className="cx-hand" />
        </span>
        <span className="cx-neck" />
        <span className="cx-nod">
          <span className="cx-head">
            <span className="cx-antenna" />
            <span className="cx-ear cx-ear-l" />
            <span className="cx-ear cx-ear-r" />
            <span className="cx-visor">
              <span className="cx-eyes">
                <span className="cx-eye" />
                <span className="cx-eye" />
              </span>
              <span className="cx-mouth" />
            </span>
            <span className="cx-shine" />
          </span>
        </span>
      </span>
    </div>
  );
}
