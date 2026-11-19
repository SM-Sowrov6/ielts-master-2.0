import {
  BookOpenTextIcon,
  FlameIcon,
  HeadphonesIcon,
  LightbulbIcon,
  MicIcon,
  PenLineIcon,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";

import { DecorativePreview } from "@/components/marketing/product-window";
import { SectionHeader } from "@/components/marketing/section-header";
import { SoonCta } from "@/components/marketing/soon-cta";

/* Illustrative demo data only: not real students, results or product claims. */
const SKILLS: readonly {
  name: string;
  band: string;
  icon: LucideIcon;
  trend: number[];
  tone: string;
}[] = [
  {
    name: "Listening",
    band: "7.0",
    icon: HeadphonesIcon,
    trend: [5.5, 6, 6, 6.5, 6.5, 7],
    tone: "blue",
  },
  {
    name: "Reading",
    band: "6.5",
    icon: BookOpenTextIcon,
    trend: [5.5, 5.5, 6, 6, 6.5, 6.5],
    tone: "indigo",
  },
  {
    name: "Writing",
    band: "6.0",
    icon: PenLineIcon,
    trend: [5, 5.5, 5.5, 5.5, 6, 6],
    tone: "emerald",
  },
  { name: "Speaking", band: "6.5", icon: MicIcon, trend: [5.5, 6, 6, 6, 6.5, 6.5], tone: "teal" },
];
const WEEK = [
  { day: "Mon", minutes: 35 },
  { day: "Tue", minutes: 50 },
  { day: "Wed", minutes: 20 },
  { day: "Thu", minutes: 65 },
  { day: "Fri", minutes: 45 },
  { day: "Sat", minutes: 80 },
  { day: "Sun", minutes: 30 },
];
const RECENT = [
  { label: "Reading practice test 3", result: "30 / 40" },
  { label: "Listening Part 3", result: "8 / 10" },
  { label: "Writing Task 2", result: "Est. 6.0" },
];

const sparkline = (values: number[]) =>
  values
    .map((v, i) => `${(i / (values.length - 1)) * 100},${(40 - ((v - 4.5) / 3) * 36).toFixed(1)}`)
    .join(" ");

/**
 * L4 · Progress (FR-PR): a header row above a modern analytics dashboard preview (overall band
 * estimate, four skill cards, weekly activity, completion, recent results) with a floating
 * streak and recommendation. All figures are sample data. Charts animate in on scroll (CSS view
 * timelines where supported); static otherwise.
 */
export function ProgressSection() {
  const maxMinutes = Math.max(...WEEK.map((d) => d.minutes));
  return (
    <section
      id="progress"
      aria-labelledby="progress-heading"
      className="relative overflow-x-clip border-y bg-surface/70 px-4 py-20 sm:px-6 lg:px-8 lg:py-28"
    >
      <div className="mx-auto max-w-[var(--container-wide)]">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <SectionHeader
            id="progress-heading"
            eyebrow="Your learning journey"
            title="See Your Progress. Reach Your Target Band."
            align="left"
          >
            Understand your learning journey through clear performance insights, skill-based
            progress tracking, and personalized improvement recommendations.
          </SectionHeader>
          <SoonCta
            href="/dashboard"
            label="Explore Your Dashboard"
            className="self-start lg:self-auto"
          />
        </div>

        <div className="relative mt-12 lg:mt-14">
          <div aria-hidden="true" className="pg-ambient absolute -inset-8 -z-10" />
          <p className="sr-only">
            Illustration: a student dashboard with sample data — an overall band estimate of 6.5
            against a target of 7.0, four skill cards, a weekly activity chart, practice completion,
            recent results, a learning streak and a recommended next step.
          </p>
          <DecorativePreview className="pg-stage">
            <div className="pg-scene">
              <div className="pg-window">
                <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3.5">
                  <span className="text-sm font-semibold">Your dashboard</span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[0.6875rem] font-medium text-muted-foreground">
                    Sample data
                  </span>
                  <span className="ml-auto rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-accent-foreground">
                    Target band 7.0
                  </span>
                </div>

                <div className="pg-grid">
                  {/* Overall band */}
                  <div className="pg-card pg-overall">
                    <span className="pg-label">Overall band · estimate</span>
                    <span className="pg-ring" style={{ "--p": 6.5 / 9 } as CSSProperties}>
                      <svg viewBox="0 0 120 120" aria-hidden="true">
                        <circle cx="60" cy="60" r="50" className="pg-ring-track" />
                        <circle cx="60" cy="60" r="50" className="pg-ring-value" pathLength="1" />
                      </svg>
                      <span className="pg-ring-text">
                        <span className="text-3xl font-bold tracking-tight tabular-nums">6.5</span>
                        <span className="text-xs text-muted-foreground">of 9</span>
                      </span>
                    </span>
                    <span className="pg-delta">+0.5 in 6 weeks</span>
                  </div>

                  {/* Skills */}
                  <div className="pg-skills">
                    {SKILLS.map((skill) => {
                      const Icon = skill.icon;
                      return (
                        <div key={skill.name} className="pg-card pg-skill" data-tone={skill.tone}>
                          <span className="flex items-center gap-2">
                            <span className="pg-skill-icon">
                              <Icon className="size-4" />
                            </span>
                            <span className="text-sm font-semibold">{skill.name}</span>
                            <span className="ml-auto text-lg font-bold tabular-nums">
                              {skill.band}
                            </span>
                          </span>
                          <svg
                            className="pg-spark"
                            viewBox="0 0 100 44"
                            preserveAspectRatio="none"
                            aria-hidden="true"
                          >
                            <polyline points={sparkline(skill.trend)} pathLength="1" />
                          </svg>
                        </div>
                      );
                    })}
                  </div>

                  {/* Weekly activity */}
                  <div className="pg-card pg-activity">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="pg-label">Weekly activity</span>
                      <span className="text-sm font-semibold tabular-nums">5 h 25 min</span>
                    </span>
                    <div className="pg-bars">
                      {WEEK.map((d, i) => (
                        <span key={d.day} className="pg-bar-col">
                          <span
                            className="pg-bar"
                            data-peak={d.minutes === maxMinutes}
                            style={
                              {
                                height: `${(d.minutes / maxMinutes) * 100}%`,
                                "--i": i,
                              } as CSSProperties
                            }
                          />
                          <span className="pg-bar-day">{d.day}</span>
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Completion + recent */}
                  <div className="pg-side">
                    <div className="pg-card pg-completion">
                      <span className="pg-ring pg-ring-sm" style={{ "--p": 0.68 } as CSSProperties}>
                        <svg viewBox="0 0 120 120" aria-hidden="true">
                          <circle cx="60" cy="60" r="50" className="pg-ring-track" />
                          <circle
                            cx="60"
                            cy="60"
                            r="50"
                            className="pg-ring-value pg-ring-emerald"
                            pathLength="1"
                          />
                        </svg>
                        <span className="pg-ring-text">
                          <span className="text-base font-bold tabular-nums">68%</span>
                        </span>
                      </span>
                      <span>
                        <span className="pg-label">Practice plan</span>
                        <span className="block text-sm font-semibold">17 of 25 sessions</span>
                      </span>
                    </div>
                    <div className="pg-card">
                      <span className="pg-label">Recent results</span>
                      <ul className="mt-2 space-y-1.5 text-sm">
                        {RECENT.map((r) => (
                          <li key={r.label} className="flex items-center justify-between gap-3">
                            <span className="truncate text-muted-foreground">{r.label}</span>
                            <span className="font-semibold tabular-nums">{r.result}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>

              {/* Floating metric cards */}
              <div className="pg-float pg-float-streak">
                <span className="pg-float-icon pg-float-icon-amber">
                  <FlameIcon className="size-4" />
                </span>
                <span>
                  <span className="block text-sm font-semibold">12-day streak</span>
                  <span className="pg-streak">
                    {Array.from({ length: 14 }, (_, i) => (
                      <i key={i} data-on={i < 12} />
                    ))}
                  </span>
                </span>
              </div>
              <div className="pg-float pg-float-tip">
                <span className="pg-float-icon">
                  <LightbulbIcon className="size-4" />
                </span>
                <span>
                  <span className="block text-xs text-muted-foreground">Recommended next</span>
                  <span className="block text-sm font-semibold">Writing Task 2 · coherence</span>
                </span>
              </div>
            </div>
          </DecorativePreview>
          <p className="mt-8 text-center text-xs text-muted-foreground">
            Dashboard figures shown here are sample data, not real results. Band scores in IELTS
            MASTER are AI estimates, not official IELTS results.
          </p>
        </div>
      </div>
    </section>
  );
}
