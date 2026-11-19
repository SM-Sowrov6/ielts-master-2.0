import {
  BookOpenIcon,
  BrainCircuitIcon,
  ClipboardCheckIcon,
  GraduationCapIcon,
  HeadphonesIcon,
  MicIcon,
  NotebookPenIcon,
  SparklesIcon,
  TargetIcon,
  TrendingUpIcon,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";

export type Tone = "blue" | "emerald" | "teal";
type Item = { label: string; icon: LucideIcon; tone: Tone };
type Strip = { id: string; direction: "ltr" | "rtl"; seconds: number; items: readonly Item[] };

export const STRIPS: readonly Strip[] = [
  {
    id: "skills",
    direction: "ltr",
    seconds: 90, // ≈ 33 px/s with four repeats per copy
    items: [
      { label: "Listening", icon: HeadphonesIcon, tone: "blue" },
      { label: "Reading", icon: BookOpenIcon, tone: "teal" },
      { label: "Writing", icon: NotebookPenIcon, tone: "blue" },
      { label: "Speaking", icon: MicIcon, tone: "emerald" },
      { label: "IELTS Preparation", icon: GraduationCapIcon, tone: "blue" },
    ],
  },
  {
    id: "features",
    direction: "rtl",
    seconds: 72, // ≈ 42 px/s
    items: [
      { label: "AI Coach", icon: BrainCircuitIcon, tone: "blue" },
      { label: "Band Score", icon: TargetIcon, tone: "emerald" },
      { label: "Mock Exam", icon: ClipboardCheckIcon, tone: "blue" },
      { label: "Progress Tracking", icon: TrendingUpIcon, tone: "teal" },
      { label: "Smart Practice", icon: SparklesIcon, tone: "blue" },
    ],
  },
];

const DEPTH_LAYERS = [1, 2, 3, 4, 5];
export const REPEATS_PER_COPY = 4;

/** A CSS-only 3D object: extruded, glossy, tilted face + floating glyph + ground shadow. */
export function Icon3D({
  icon: Icon,
  tone,
  delay,
}: {
  icon: LucideIcon;
  tone: Tone;
  delay: number;
}) {
  return (
    <span
      className="icon3d"
      data-tone={tone}
      style={{ "--float-delay": `${delay}s` } as CSSProperties}
    >
      <span className="icon3d-shadow" />
      <span className="icon3d-float">
        <span className="icon3d-body">
          {DEPTH_LAYERS.map((layer) => (
            <span
              key={layer}
              className="icon3d-depth"
              style={{ "--layer": layer } as CSSProperties}
            />
          ))}
          <span className="icon3d-face" />
          <span className="icon3d-glyph">
            <Icon />
          </span>
        </span>
      </span>
    </span>
  );
}

function StripCopy({ strip, copy }: { strip: Strip; copy: number }) {
  // One copy must always be wider than the widest screen (2560px+), otherwise empty space shows
  // before the loop restarts. Four repeats of the slim pills is about 3,000px.
  const items = Array.from({ length: REPEATS_PER_COPY }, () => strip.items).flat();
  return (
    <ul className="flex shrink-0 gap-3 pr-3 sm:gap-3.5 sm:pr-3.5">
      {items.map((item, i) => (
        <li
          key={`${copy}-${i}`}
          className="surface-sheen flex items-center gap-2.5 rounded-full border bg-card py-1.5 pr-4 pl-2 shadow-elevation-1 sm:gap-3 sm:py-2 sm:pr-5 sm:pl-2.5"
        >
          <Icon3D icon={item.icon} tone={item.tone} delay={-((i * 0.7 + copy * 0.35) % 5.5)} />
          <span className="font-heading text-sm font-semibold tracking-tight whitespace-nowrap sm:text-[0.9375rem]">
            {item.label}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Two looping strips of IELTS topics directly below the hero (a third strip was removed at the
 * Product Owner's request). Strip 1 moves left to right, strip 2 right to left, at different speeds. The moving strips are decorative
 * (aria-hidden); screen readers get the topics once as a plain list.
 */
export function SkillMarquee() {
  const topics = [...new Set(STRIPS.flatMap((s) => s.items.map((i) => i.label)))];
  return (
    <section aria-label="What IELTS MASTER covers" className="border-b py-6 sm:py-8">
      <ul className="sr-only">
        {topics.map((topic) => (
          <li key={topic}>{topic}</li>
        ))}
      </ul>
      <div aria-hidden="true" className="flex flex-col gap-2 sm:gap-3">
        {STRIPS.map((strip) => (
          <div
            key={strip.id}
            className="marquee py-1.5"
            data-direction={strip.direction}
            data-strip={strip.id}
            style={{ "--marquee-duration": `${strip.seconds}s` } as CSSProperties}
          >
            <div className="marquee-track">
              <StripCopy strip={strip} copy={0} />
              <StripCopy strip={strip} copy={1} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
