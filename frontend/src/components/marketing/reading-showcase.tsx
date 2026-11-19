import {
  BookOpenTextIcon,
  HighlighterIcon,
  ListChecksIcon,
  PanelsLeftRightIcon,
  ScanTextIcon,
} from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { DecorativePreview } from "@/components/marketing/product-window";
import { ReadingDemo } from "@/components/marketing/reading-demo";
import { TiltScene } from "@/components/marketing/tilt-scene";
import { Button } from "@/components/ui/button";

const FEATURES = [
  { icon: PanelsLeftRightIcon, text: "Passage and questions side by side" },
  { icon: ScanTextIcon, text: "Jump to any labelled paragraph" },
  { icon: HighlighterIcon, text: "Highlight text and keep private notes" },
  { icon: ListChecksIcon, text: "Every Reading question type, Academic and General Training" },
] as const;

const RIM_LAYERS = [1, 2, 3, 4, 5, 6];

/**
 * Module 02 · Reading, flagship showcase: an introduction above a near full-width floating 3D
 * display running a sample Reading test, with a looping demo (select text → answer → type).
 * Copy follows FR-RL-01/02/05/06; "Explore Reading" leads to the Practice area, still marked
 * "coming soon".
 */
export function ReadingShowcase() {
  return (
    <section
      id="reading"
      aria-labelledby="reading-heading"
      data-visual-side="full"
      className="rx-section relative overflow-x-clip border-b"
    >
      <div className="mx-auto max-w-[var(--container-wide)] px-4 pt-20 pb-24 sm:px-6 lg:px-8 lg:pt-28 lg:pb-32">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold text-primary shadow-elevation-1">
            <span
              aria-hidden="true"
              className="grid size-5 place-items-center rounded-full bg-accent text-accent-foreground"
            >
              <BookOpenTextIcon className="size-3" />
            </span>
            Module 02 · Reading
          </p>
          <h3
            id="reading-heading"
            className="mt-5 font-heading text-4xl leading-[1.05] font-bold tracking-[-0.03em] text-balance sm:text-5xl lg:text-[3.5rem]"
          >
            Read Smarter. <span className="text-brand-gradient">Understand Deeper.</span>
          </h3>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
            Work through real exam-style passages in a focused split view: find the evidence in the
            text, answer with confidence, and see how every question type is built.
          </p>
          <ul className="mt-8 grid w-full gap-3 text-left text-sm sm:grid-cols-2 lg:w-[min(64rem,calc(100vw-4rem))] lg:max-w-none lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li
                key={text}
                className="flex items-start gap-3 rounded-xl border bg-card/70 px-4 py-3 shadow-elevation-1"
              >
                <span
                  aria-hidden="true"
                  className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground"
                >
                  <Icon className="size-4" />
                </span>
                <span className="pt-1 leading-snug">{text}</span>
              </li>
            ))}
          </ul>
          <Button asChild className="mt-8 h-11 px-5 text-[0.9375rem] shadow-elevation-2">
            <Link href="/reading">Explore Reading</Link>
          </Button>
        </div>

        <div className="relative mt-14 lg:mt-16">
          <div aria-hidden="true" className="rx-glow absolute -inset-x-10 -inset-y-16 -z-10" />
          <p className="sr-only">
            Illustration: a large screen showing an IELTS Reading practice test. A cursor selects
            the phrase &ldquo;artificial light&rdquo; in the passage, moves to question 19 and types
            it into the answer field, which is then saved.
          </p>
          <DecorativePreview className="rx-stage rx-reveal">
            <TiltScene className="rx-scene">
              <div className="rx-float">
                <div className="rx-display">
                  {RIM_LAYERS.map((layer) => (
                    <div
                      key={layer}
                      className="rx-rim"
                      style={{ "--layer": layer } as CSSProperties}
                    />
                  ))}
                  <div className="rx-bezel">
                    <div className="rx-screen">
                      <ReadingDemo />
                    </div>
                    <span className="rx-chin">IELTS MASTER</span>
                  </div>
                </div>
              </div>
            </TiltScene>
            <div className="rx-floor" />
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
