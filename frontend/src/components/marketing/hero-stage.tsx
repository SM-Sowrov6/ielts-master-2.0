import { CheckIcon, Clock3Icon, HeadphonesIcon, PenLineIcon } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { DecorativePreview, ProductWindow } from "@/components/marketing/product-window";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { cn } from "@/lib/utils";

/** CSS custom properties for a layer: depth (translateZ) and entrance delay. */
function layer(z: number, delay: number): CSSProperties {
  return { "--z": `${z}px`, "--delay": `${delay}ms` } as CSSProperties;
}

/**
 * Hero illustration: a Reading practice window with floating cards at different depths.
 * Purely decorative (aria-hidden + inert); the sr-only sentence describes it once.
 * All passage text is original synthetic content; figures are labelled as samples.
 */
export function HeroStage() {
  return (
    <div className="relative">
      <p className="sr-only">
        Illustration of the practice interface: a Reading passage with a True, False or Not Given
        question, a sample band estimate, a Listening audio player and a Writing word counter.
      </p>
      <DecorativePreview className="hero-stage px-2 pt-16 pb-12 sm:px-6 sm:pt-24 lg:pt-20 lg:pb-8">
        <div className="hero-floor" />
        <TiltScene className="hero-scene">
          <div className="hero-plate" />
          <div className="hero-base enter-rise" style={layer(0, 80)}>
            <ReadingWindow />
          </div>
          <FloatingCard
            className="-top-14 -left-1 w-44 sm:-top-20 sm:-left-6 sm:w-48"
            style={layer(90, 260)}
          >
            <BandEstimateCard />
          </FloatingCard>
          <FloatingCard
            className="-top-20 right-3 hidden w-52 sm:block lg:-right-5"
            style={layer(60, 380)}
          >
            <WritingCard />
          </FloatingCard>
          <FloatingCard
            className="-right-1 -bottom-8 w-60 sm:right-auto sm:-bottom-10 sm:left-10 sm:w-72"
            style={layer(130, 500)}
          >
            <AudioCard />
          </FloatingCard>
        </TiltScene>
      </DecorativePreview>
    </div>
  );
}

function FloatingCard({
  children,
  className,
  style,
}: {
  children: ReactNode;
  className?: string;
  style: CSSProperties;
}) {
  return (
    <div className={cn("hero-layer", className)} style={style}>
      <div className="enter-rise">
        <div className="surface-sheen rounded-xl border bg-card p-3.5 text-card-foreground shadow-elevation-float">
          {children}
        </div>
      </div>
    </div>
  );
}

function ReadingWindow() {
  const palette = Array.from({ length: 13 }, (_, i) => i + 1);
  return (
    <ProductWindow title="Reading practice · Passage 1">
      <div className="grid sm:grid-cols-[1.1fr_1fr]">
        <div className="space-y-2.5 border-b p-4 text-xs leading-relaxed sm:border-r sm:border-b-0 sm:p-5">
          <p className="text-[0.6875rem] font-semibold tracking-wide text-primary uppercase">
            Passage 1
          </p>
          <p className="font-heading text-sm font-semibold">The return of the city river</p>
          <p className="text-muted-foreground">
            <span className="mr-1.5 font-semibold text-foreground">A</span>
            For much of the twentieth century, small rivers that once crossed European cities were
            buried beneath roads. Covered channels were cheaper to maintain, and the water was
            rarely seen as an asset.
          </p>
          <p className="hidden text-muted-foreground sm:block">
            <span className="mr-1.5 font-semibold text-foreground">B</span>
            Since the 1990s, several cities have reversed this decision.{" "}
            <span className="rounded-sm bg-accent px-0.5 text-accent-foreground">
              Opening the channels again has reduced flood risk
            </span>{" "}
            in some districts, although the benefits depend on local rainfall.
          </p>
        </div>
        <div className="space-y-3 p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold">Questions 1–5</span>
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] font-medium tabular-nums">
              <Clock3Icon className="size-3 text-primary" />
              18:42
            </span>
          </div>
          <span className="inline-block rounded-full bg-accent px-2 py-0.5 text-[0.6875rem] font-medium text-accent-foreground">
            True / False / Not Given
          </span>
          <p className="text-xs font-medium">1. Covered river channels cost less to maintain.</p>
          <div className="space-y-1.5">
            {(["TRUE", "FALSE", "NOT GIVEN"] as const).map((choice) => {
              const selected = choice === "TRUE";
              return (
                <div
                  key={choice}
                  className={cn(
                    "flex items-center justify-between rounded-md border px-2.5 py-1.5 text-[0.6875rem] font-medium",
                    selected && "border-primary bg-primary/5 text-primary",
                  )}
                >
                  {choice}
                  <span
                    className={cn(
                      "grid size-3.5 place-items-center rounded-full border-[1.5px]",
                      selected ? "border-primary bg-primary" : "border-input",
                    )}
                  >
                    {selected && <span className="size-1.5 rounded-full bg-primary-foreground" />}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-1.5 rounded-md bg-success/10 px-2.5 py-1.5 text-[0.6875rem] font-medium text-success">
            <CheckIcon className="size-3.5 shrink-0" />
            Correct · paragraph A
          </div>
          <div className="grid grid-cols-7 gap-1 pt-1">
            {palette.map((n) => (
              <span
                key={n}
                className={cn(
                  "grid h-5 place-items-center rounded-sm text-[0.625rem] font-semibold tabular-nums",
                  n <= 4 && "bg-primary text-primary-foreground",
                  n === 5 && "border border-warning text-warning",
                  n > 5 && "bg-muted text-muted-foreground",
                  n === 1 && "ring-2 ring-primary/30",
                )}
              >
                {n}
              </span>
            ))}
          </div>
        </div>
      </div>
    </ProductWindow>
  );
}

function BandEstimateCard() {
  const skills = [
    { label: "L", value: 7.5 },
    { label: "R", value: 7.0 },
    { label: "W", value: 6.5 },
    { label: "S", value: 7.0 },
  ];
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[0.6875rem] font-semibold whitespace-nowrap text-muted-foreground">
          Band estimate
        </span>
        <span className="rounded-full bg-muted px-1.5 py-px text-[0.625rem] font-medium text-muted-foreground">
          Sample
        </span>
      </div>
      <p className="font-heading text-3xl leading-none font-bold tracking-tight text-primary tabular-nums">
        7.0
      </p>
      <div className="space-y-1">
        {skills.map((skill) => (
          <div key={skill.label} className="flex items-center gap-2 text-[0.625rem] font-medium">
            <span className="w-2.5 text-muted-foreground">{skill.label}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-primary"
                style={{ width: `${(skill.value / 9) * 100}%` }}
              />
            </span>
            <span className="w-5 text-right tabular-nums">{skill.value.toFixed(1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WritingCard() {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[0.6875rem] font-semibold text-muted-foreground">
        <span className="grid size-6 place-items-center rounded-md bg-accent text-accent-foreground">
          <PenLineIcon className="size-3.5" />
        </span>
        Writing · Task 2
      </div>
      <p className="font-heading text-xl leading-none font-bold tabular-nums">
        268 <span className="text-xs font-medium text-muted-foreground">words</span>
      </p>
      <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
        <span className="block h-full w-full rounded-full bg-brand-accent" />
      </span>
      <p className="flex items-center gap-1 text-[0.6875rem] font-medium text-success">
        <CheckIcon className="size-3" /> Minimum 250 reached
      </p>
    </div>
  );
}

const WAVE = [30, 55, 80, 45, 95, 70, 40, 85, 60, 35, 75, 50, 90, 45, 65, 30, 55, 40];

function AudioCard() {
  return (
    <div className="flex items-center gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground shadow-elevation-2">
        <HeadphonesIcon className="size-4.5" />
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-center justify-between gap-2 text-[0.6875rem]">
          <span className="truncate font-semibold">Listening · Section 2</span>
          <span className="shrink-0 text-muted-foreground tabular-nums">03:18 / 07:40</span>
        </div>
        <div className="flex h-6 items-end gap-[3px]">
          {WAVE.map((height, i) => (
            <span
              key={i}
              className={cn("w-full rounded-full", i < 8 ? "bg-primary" : "bg-brand-accent/45")}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
