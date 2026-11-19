import { FileTextIcon, ListChecksIcon, PenLineIcon, TimerIcon } from "lucide-react";
import Link from "next/link";

import { DecorativePreview } from "@/components/marketing/product-window";
import { WritingDemo } from "@/components/marketing/writing-demo";
import { Button } from "@/components/ui/button";

const FEATURES = [
  { icon: PenLineIcon, text: "Task 1 and Task 2, Academic and General Training" },
  { icon: FileTextIcon, text: "Live word count as you write" },
  { icon: TimerIcon, text: "Timed, exam-style practice" },
  { icon: ListChecksIcon, text: "Feedback on all four Writing criteria" },
] as const;

/**
 * Module 03 · Writing, flagship showcase: an introduction above a large, frontal 3D MacBook whose
 * keyboard types a sample essay into the Writing editor on screen, watched by the AI mascot on
 * the lid. Copy follows FR-WR; on-screen figures are marked as samples. "Explore Writing" leads
 * to the Practice area, still marked "coming soon".
 */
export function WritingShowcase() {
  return (
    <section
      id="writing"
      aria-labelledby="writing-heading"
      data-visual-side="full"
      className="wx-section relative overflow-x-clip border-b"
    >
      <div className="mx-auto max-w-[var(--container-wide)] px-4 pt-20 pb-16 sm:px-6 lg:px-8 lg:pt-28 lg:pb-20">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold text-primary shadow-elevation-1">
            <span
              aria-hidden="true"
              className="grid size-5 place-items-center rounded-full bg-accent text-accent-foreground"
            >
              <PenLineIcon className="size-3" />
            </span>
            Module 03 · Writing
          </p>
          <h3
            id="writing-heading"
            className="mt-5 font-heading text-4xl leading-[1.05] font-bold tracking-[-0.03em] text-balance sm:text-5xl lg:text-[3.5rem]"
          >
            Write with Confidence. <span className="text-brand-gradient">Achieve More.</span>
          </h3>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
            Practise Task 1 and Task 2 in a calm, exam-style editor that keeps count of every word,
            and build essays that answer the question with clear, well-organised ideas.
          </p>
          <ul className="mt-7 flex flex-wrap justify-center gap-2 text-sm">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li
                key={text}
                className="flex items-center gap-2 rounded-full border bg-card/80 py-1.5 pr-3.5 pl-1.5 shadow-elevation-1"
              >
                <span
                  aria-hidden="true"
                  className="grid size-6 place-items-center rounded-full bg-accent text-accent-foreground"
                >
                  <Icon className="size-3.5" />
                </span>
                {text}
              </li>
            ))}
          </ul>
          <Button asChild className="mt-8 h-11 px-5 text-[0.9375rem] shadow-elevation-2">
            <Link href="/writing">Explore Writing</Link>
          </Button>
        </div>

        <div className="relative mt-10 lg:mt-12">
          <div aria-hidden="true" className="wx-glow absolute inset-x-0 -inset-y-10 -z-10" />
          <DecorativePreview className="wx-stage wx-reveal">
            <WritingDemo />
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
