import { ArrowRightIcon, CheckIcon, Clock3Icon, HeadphonesIcon, PauseIcon } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { DecorativePreview } from "@/components/marketing/product-window";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FEATURES = [
  "All four parts in the order and format of the real test",
  "Form, note, table, flow-chart and map completion, plus multiple choice and matching",
  "Answers checked with IELTS rules: word limits, numbers, British and American spelling",
  "Practice mode with replay, or exam mode with single-play audio and strict timing",
] as const;

/**
 * Module 01 · Listening, flagship showcase: a CSS 3D MacBook running a sample Listening screen,
 * with floating 3D objects. Server Component except the pointer-tilt wrapper (TiltScene).
 * Everything inside the stage is decorative (aria-hidden + inert); the sr-only sentence
 * describes it once. Copy follows FR-RL / FR-EX-12 and does not claim unbuilt availability:
 * "Explore Listening" opens the candidate Listening page (built; sign-in is requested first when
 * needed, then the visitor returns to /listening).
 */
export function ListeningShowcase() {
  return (
    <section
      id="listening"
      aria-labelledby="listening-heading"
      data-visual-side="right"
      className="lx-section relative overflow-x-clip border-b bg-surface"
    >
      <div className="mx-auto grid max-w-[var(--container-wide)] grid-cols-1 items-center gap-6 px-4 pt-20 pb-10 sm:px-6 lg:grid-cols-12 lg:gap-6 lg:px-8 lg:py-28">
        <div className="flex min-w-0 flex-col items-start gap-5 lg:col-span-5">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold text-primary shadow-elevation-1">
            <span
              aria-hidden="true"
              className="grid size-5 place-items-center rounded-full bg-accent text-accent-foreground"
            >
              <HeadphonesIcon className="size-3" />
            </span>
            Module 01 · Listening
          </p>
          <h3
            id="listening-heading"
            className="font-heading text-4xl leading-[1.05] font-bold tracking-[-0.03em] text-balance sm:text-5xl"
          >
            Master IELTS <span className="text-brand-gradient">Listening</span>
          </h3>
          <p className="max-w-xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
            Train your ear on test-style recordings and questions, in a clean exam interface that
            feels like test day, then see exactly where every mark was won or lost.
          </p>
          <ul className="mt-1 grid w-full gap-3 text-[0.9375rem]">
            {FEATURES.map((feature) => (
              <li key={feature} className="flex items-start gap-3">
                <span
                  aria-hidden="true"
                  className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-success/10 text-success"
                >
                  <CheckIcon className="size-3.5" />
                </span>
                <span>{feature}</span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <Button asChild className="h-11 px-5 text-[0.9375rem] shadow-elevation-2">
              <Link href="/listening">
                Explore Listening
                <ArrowRightIcon aria-hidden="true" data-icon="inline-end" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-11 px-5 text-[0.9375rem]">
              <Link href="/register">
                Create your account
                <ArrowRightIcon aria-hidden="true" data-icon="inline-end" />
              </Link>
            </Button>
          </div>
        </div>

        <div className="relative min-w-0 lg:col-span-7">
          <div aria-hidden="true" className="lx-glow absolute -inset-10 -z-10" />
          <p className="sr-only">
            Illustration: a laptop showing the IELTS MASTER Listening practice screen, with an audio
            player, a multiple-choice question and question navigation, surrounded by headphones, an
            audio card and progress indicators.
          </p>
          <DecorativePreview className="lx-stage lx-reveal px-3 pt-14 pb-[22%] sm:px-8 sm:pt-16 lg:pt-10">
            <TiltScene className="lx-scene">
              <div className="lx-float">
                <MacBook />
              </div>
              <FloatingObjects />
            </TiltScene>
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}

const KEYS = Array.from({ length: 84 }, (_, i) => i);
const RIM_LAYERS = [1, 2, 3, 4, 5, 6, 7, 8];

function MacBook() {
  return (
    <div className="lx-device">
      <div className="lx-lid">
        <div className="lx-notch" />
        <div className="lx-screen">
          <ListeningApp />
        </div>
      </div>
      <div className="lx-base">
        <div className="lx-floor" />
        {RIM_LAYERS.map((layer) => (
          <div key={layer} className="lx-rim" style={{ "--layer": layer } as CSSProperties} />
        ))}
        <div className="lx-hinge" />
        <div className="lx-keys">
          {KEYS.map((key) => (
            <span key={key} />
          ))}
        </div>
        <div className="lx-trackpad" />
      </div>
    </div>
  );
}

const WAVE = [
  34, 52, 70, 46, 88, 64, 40, 76, 58, 92, 50, 36, 66, 84, 44, 72, 54, 30, 62, 80, 48, 68, 38, 86,
  56, 42, 74, 60, 34, 70, 52, 82, 46, 64, 40, 58,
];

function Waveform({ bars, played, accent }: { bars: number[]; played: number; accent?: boolean }) {
  return (
    <div className="lx-wave">
      {bars.map((height, i) => (
        <span
          key={i}
          style={
            {
              "--h": `${height}%`,
              "--d": `${-((i * 0.13) % 1.4)}s`,
              "--bar":
                i < played
                  ? "var(--primary)"
                  : accent
                    ? "color-mix(in oklch, var(--brand-accent) 55%, transparent)"
                    : "color-mix(in oklch, var(--primary) 22%, transparent)",
            } as CSSProperties
          }
        />
      ))}
    </div>
  );
}

/** The sample Listening practice screen shown on the laptop (decorative, sample content). */
function ListeningApp() {
  const options = [
    ["A", "It is closer to the city centre."],
    ["B", "It has better sports facilities."],
    ["C", "It offers smaller class sizes."],
  ] as const;
  return (
    <div className="lx-app flex flex-col bg-background text-foreground">
      <div className="flex h-[3.2em] shrink-0 items-center gap-3 border-b bg-card px-4">
        <span className="flex items-center gap-2 text-sm font-bold tracking-tight">
          <span className="grid size-[1.7em] place-items-center rounded-[0.45em] bg-primary text-primary-foreground">
            <HeadphonesIcon className="size-[0.95em]" />
          </span>
          IELTS <span className="-ml-1.5 text-primary">MASTER</span>
        </span>
        <span className="mx-auto flex items-center gap-2 text-xs text-muted-foreground">
          Listening · Practice test
          <span className="rounded-full bg-muted px-2 py-px font-medium">Sample</span>
        </span>
        <span className="flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-semibold tabular-nums">
          <Clock3Icon className="size-[1em] text-primary" />
          24:18
        </span>
        <span className="grid size-[1.9em] place-items-center rounded-full bg-primary text-[0.7em] font-semibold text-primary-foreground">
          AR
        </span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[1.05fr_1fr] gap-3 p-3.5">
        <div className="flex min-h-0 flex-col gap-3">
          <div className="space-y-2.5 rounded-[0.75em] border bg-card p-3 shadow-elevation-1">
            <div className="flex items-center gap-2.5">
              <span className="grid size-[2.5em] shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-elevation-2">
                <PauseIcon className="size-[1.1em]" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold">Part 2 · Campus tour</p>
                <p className="text-xs text-muted-foreground">Questions 11–20</p>
              </div>
            </div>
            <div className="h-[3em]">
              <Waveform bars={WAVE} played={16} />
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground tabular-nums">
              03:24
              <span className="relative h-[0.35em] flex-1 rounded-full bg-muted">
                <span className="absolute inset-y-0 left-0 w-[44%] rounded-full bg-primary" />
                <span className="absolute top-1/2 left-[44%] size-[0.8em] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-primary" />
              </span>
              08:10
            </div>
          </div>
          <div className="grid grid-cols-4 gap-1.5 text-xs font-medium">
            {(["done", "now", "next", "next"] as const).map((state, i) => (
              <span
                key={i}
                className={cn(
                  "flex items-center justify-center gap-1 rounded-[0.5em] py-1.5",
                  state === "done" && "bg-success/12 text-success",
                  state === "now" && "bg-primary text-primary-foreground",
                  state === "next" && "bg-muted text-muted-foreground",
                )}
              >
                {state === "done" && <CheckIcon className="size-[0.9em]" />}
                Part {i + 1}
              </span>
            ))}
          </div>
          <div className="flex-1 space-y-1.5 rounded-[0.75em] border border-dashed bg-surface p-3 text-xs leading-relaxed text-muted-foreground">
            <p className="font-semibold text-foreground">Instructions</p>
            <p>
              You will hear a guide describing a campus tour. First, look at questions 11 to 15.
            </p>
          </div>
          <div className="space-y-1.5 rounded-[0.75em] border bg-card p-3">
            <div className="flex justify-between text-xs">
              <span className="font-medium">Test progress</span>
              <span className="font-semibold text-primary tabular-nums">14 / 40</span>
            </div>
            <span className="block h-[0.4em] rounded-full bg-muted">
              <span className="block h-full w-[35%] rounded-full bg-linear-to-r from-primary to-brand-accent" />
            </span>
          </div>
        </div>
        <div className="flex min-h-0 flex-col rounded-[0.75em] border bg-card p-3 shadow-elevation-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold">Questions 11–15</span>
            <span className="rounded-full bg-accent px-2 py-px text-xs font-medium text-accent-foreground">
              Multiple choice
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Choose the correct letter, A, B or C.
          </p>
          <p className="mt-2.5 text-sm leading-snug font-semibold">
            <span className="mr-1.5 text-primary">12</span>
            Why did the speaker choose the Riverside campus?
          </p>
          <div className="mt-2.5 space-y-1.5">
            {options.map(([letter, text]) => {
              const selected = letter === "B";
              return (
                <div
                  key={letter}
                  className={cn(
                    "flex items-center gap-2 rounded-[0.55em] border px-2.5 py-1.5 text-xs",
                    selected && "border-primary bg-primary/6",
                  )}
                >
                  <span
                    className={cn(
                      "grid size-[1.5em] shrink-0 place-items-center rounded-full text-[0.85em] font-bold",
                      selected
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {letter}
                  </span>
                  <span className={cn(selected && "font-medium")}>{text}</span>
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-sm leading-snug font-semibold">
            <span className="mr-1.5 text-primary">13</span>
            What does the speaker say about the library?
          </p>
          <div className="mt-2 space-y-1.5">
            {[
              "It closes early on Fridays.",
              "It was recently extended.",
              "It is open to visitors.",
            ].map((text, i) => (
              <div
                key={text}
                className="flex items-center gap-2 rounded-[0.55em] border px-2.5 py-1.5 text-xs"
              >
                <span className="grid size-[1.5em] shrink-0 place-items-center rounded-full bg-muted text-[0.85em] font-bold text-muted-foreground">
                  {["A", "B", "C"][i]}
                </span>
                {text}
              </div>
            ))}
          </div>
          <div className="mt-auto grid grid-cols-10 gap-1 pt-3">
            {Array.from({ length: 10 }, (_, i) => i + 11).map((n) => (
              <span
                key={n}
                className={cn(
                  "grid h-[1.6em] place-items-center rounded-[0.35em] text-[0.7em] font-semibold tabular-nums",
                  n < 12 && "bg-primary text-primary-foreground",
                  n === 12 && "bg-primary/15 text-primary ring-1 ring-primary",
                  n > 12 && "bg-muted text-muted-foreground",
                )}
              >
                {n}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function FloatingObjects() {
  return (
    <>
      {/* 3D headphones */}
      <div
        className="lx-obj -top-12 -left-2 scale-75 sm:-top-14 sm:-left-4 sm:scale-90 lg:-top-12 lg:left-[2%]"
        style={{ "--z": "140px" } as CSSProperties}
      >
        <div className="lx-bob" style={{ "--delay": "-1s" } as CSSProperties}>
          <div className="lx-obj-inner">
            <div className="lx-hp">
              <div className="lx-hp-band" />
              {(["left", "right"] as const).map((side) => (
                <div key={side} className="lx-hp-cup" data-side={side}>
                  {[1, 2, 3, 4].map((layer) => (
                    <span
                      key={layer}
                      className="lx-hp-depth"
                      style={{ "--layer": layer } as CSSProperties}
                    />
                  ))}
                  <span className="lx-hp-face" />
                </div>
              ))}
              <div className="lx-hp-shadow" />
            </div>
          </div>
        </div>
      </div>

      {/* Audio card with frequency visualisation */}
      <div
        className="lx-obj bottom-[3%] left-0 w-44 sm:bottom-[10%] sm:w-64 lg:left-[4%]"
        style={{ "--z": "170px", "--obj-ry": "10deg" } as CSSProperties}
      >
        <div className="lx-bob" style={{ "--delay": "-3s" } as CSSProperties}>
          <div className="lx-obj-inner lx-card flex items-center gap-3 p-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-elevation-2">
              <HeadphonesIcon className="size-4.5" />
            </span>
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex items-center justify-between gap-2 text-[0.6875rem]">
                <span className="truncate font-semibold">Now playing · Part 2</span>
                <span className="text-muted-foreground tabular-nums">03:24</span>
              </div>
              <div className="h-7">
                <Waveform bars={WAVE.slice(0, 22)} played={9} accent />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Progress ring */}
      <div
        className="lx-obj -top-8 right-0 hidden sm:block lg:-right-6"
        style={{ "--z": "240px", "--obj-ry": "-12deg" } as CSSProperties}
      >
        <div className="lx-bob" style={{ "--delay": "-5s" } as CSSProperties}>
          <div className="lx-obj-inner lx-card flex items-center gap-3 p-3 pr-4">
            <span className="relative grid size-12 place-items-center">
              <span
                className="lx-ring absolute inset-0 rounded-full"
                style={{ "--p": 35 } as CSSProperties}
              />
              <span className="text-xs font-bold tabular-nums">35%</span>
            </span>
            <span className="text-[0.6875rem] leading-tight">
              <span className="block font-semibold">Part 2 of 4</span>
              <span className="text-muted-foreground">14 of 40 answered</span>
            </span>
          </div>
        </div>
      </div>

      {/* Saved answer card */}
      <div
        className="lx-obj -right-2 bottom-[30%] hidden md:block lg:-right-8"
        style={{ "--z": "230px", "--obj-ry": "-8deg" } as CSSProperties}
      >
        <div className="lx-bob" style={{ "--delay": "-2s" } as CSSProperties}>
          <div className="lx-obj-inner lx-card flex items-center gap-2.5 px-3 py-2.5">
            <span className="grid size-7 place-items-center rounded-full bg-success/15 text-success">
              <CheckIcon className="size-4" />
            </span>
            <span className="text-[0.6875rem] leading-tight">
              <span className="block font-semibold">Question 12 · B</span>
              <span className="text-muted-foreground">Answer saved</span>
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
