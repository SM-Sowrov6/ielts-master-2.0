import {
  ArrowRightIcon,
  BookOpenTextIcon,
  HeadphonesIcon,
  LayoutGridIcon,
  LineChartIcon,
  MessageSquareTextIcon,
  MicIcon,
  PenLineIcon,
  UserRoundPlusIcon,
} from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { soonLabel } from "@/components/layout/soon-badge";
import { DecorativePreview } from "@/components/marketing/product-window";
import { SectionHeader } from "@/components/marketing/section-header";
import { Icon3D } from "@/components/marketing/skill-marquee";
import { Button } from "@/components/ui/button";

const STEPS = [
  {
    icon: UserRoundPlusIcon,
    title: "Create Your Account",
    text: "Start your IELTS preparation journey with your personal learning space.",
  },
  {
    icon: LayoutGridIcon,
    title: "Choose Your Practice",
    text: "Explore Listening, Reading, Writing, Speaking, and mock exam preparation.",
  },
  {
    icon: MessageSquareTextIcon,
    title: "Learn with AI Guidance",
    text: "Use AI-powered feedback and recommendations to understand where you can improve.",
  },
  {
    icon: LineChartIcon,
    title: "Track Your Progress",
    text: "Monitor your practice journey and keep working toward your target band.",
  },
] as const;

/**
 * L4 · How it works: a connected four-step journey. 3D number discs on a line that draws itself
 * as the section scrolls into view; each step reveals in turn (CSS view timelines where
 * supported, static otherwise). Horizontal from 64rem, vertical below.
 */
export function HowItWorksSection() {
  return (
    <section
      id="how-it-works"
      aria-labelledby="how-it-works-heading"
      className="relative overflow-x-clip px-4 py-20 sm:px-6 lg:px-8 lg:py-28"
    >
      <div className="mx-auto max-w-[var(--container-wide)]">
        <SectionHeader
          id="how-it-works-heading"
          eyebrow="Get started in simple steps"
          title="Your IELTS Journey, Made Simpler."
        >
          A clear path from your first practice session to confident exam preparation.
        </SectionHeader>
        <ol className="hw-steps">
          <span aria-hidden="true" className="hw-line">
            <span className="hw-line-fill" />
          </span>
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="hw-step" style={{ "--i": i } as CSSProperties}>
              <span aria-hidden="true" className="hw-disc">
                <span className="hw-disc-depth" />
                <span className="hw-disc-face">{String(i + 1).padStart(2, "0")}</span>
              </span>
              <div className="hw-content">
                <span aria-hidden="true" className="hw-icon">
                  <Icon className="size-4" />
                </span>
                <h3 className="mt-3 font-heading text-lg font-semibold">
                  <span className="sr-only">Step {i + 1}: </span>
                  {title}
                </h3>
                <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">
                  {text}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

const ORBIT = [
  { icon: HeadphonesIcon, tone: "blue", label: "Listening" },
  { icon: BookOpenTextIcon, tone: "teal", label: "Reading" },
  { icon: PenLineIcon, tone: "emerald", label: "Writing" },
  { icon: MicIcon, tone: "blue", label: "Speaking" },
] as const;

/**
 * L4 · Final call to action: a royal-blue to emerald panel with a CSS-3D target emblem and the
 * four skills floating around it. "Get Started" leads to registration (works today); "Explore
 * Practice" leads to the Practice area, still marked "coming soon".
 */
export function FinalCtaSection() {
  return (
    <section
      id="get-started"
      aria-labelledby="final-cta-heading"
      className="px-4 pb-20 sm:px-6 lg:px-8 lg:pb-28"
    >
      <div className="fc-panel relative isolate mx-auto max-w-[var(--container-wide)] overflow-hidden rounded-[2rem] text-white">
        <div aria-hidden="true" className="fc-light absolute inset-0 -z-10" />
        <div className="grid items-center gap-10 px-6 py-14 sm:px-12 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:py-16">
          <div>
            <h2
              id="final-cta-heading"
              className="font-heading text-4xl font-bold tracking-[-0.03em] text-balance sm:text-5xl lg:text-[3.5rem] lg:leading-[1.05]"
            >
              Your IELTS Goal Starts Here.
            </h2>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-pretty text-white/85 sm:text-lg">
              Build your confidence, practise smarter, and take the next step toward your target
              IELTS band.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Button
                asChild
                className="group h-12 bg-white px-6 text-[0.9375rem] font-semibold text-[#1d4ed8] shadow-[0_14px_30px_-12px_rgb(2_6_23/0.5)] transition-[transform,box-shadow,background-color] hover:-translate-y-0.5 hover:bg-white/95"
              >
                <Link href="/register">
                  Get Started
                  <ArrowRightIcon
                    aria-hidden="true"
                    className="size-4 transition-transform group-hover:translate-x-0.5"
                  />
                </Link>
              </Button>
              <Button
                asChild
                variant="outline"
                className="h-12 border-white/45 bg-white/5 px-6 text-[0.9375rem] text-white backdrop-blur-sm transition-[transform,background-color] hover:-translate-y-0.5 hover:bg-white/15 hover:text-white dark:border-white/45 dark:bg-white/5 dark:hover:bg-white/15"
              >
                <Link href="/practice" aria-label={soonLabel("Explore Practice")}>
                  Explore Practice
                  <span className="rounded-full bg-white/20 px-1.5 py-px text-[0.625rem] font-semibold tracking-wide uppercase">
                    Soon
                  </span>
                </Link>
              </Button>
            </div>
          </div>

          <DecorativePreview className="fc-stage">
            <div className="fc-emblem">
              <span className="fc-ring fc-ring-1" />
              <span className="fc-ring fc-ring-2" />
              <span className="fc-ring fc-ring-3" />
              <span className="fc-core">
                <span className="fc-core-label">Your target</span>
              </span>
              {ORBIT.map((item, i) => (
                <span key={item.label} className="fc-orbit" style={{ "--i": i } as CSSProperties}>
                  <Icon3D icon={item.icon} tone={item.tone} delay={-i * 1.2} />
                  <span className="fc-orbit-label">{item.label}</span>
                </span>
              ))}
            </div>
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
