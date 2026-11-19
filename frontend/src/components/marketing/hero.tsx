import { ArrowRightIcon, CheckIcon } from "lucide-react";
import Link from "next/link";

import { HeroStage } from "@/components/marketing/hero-stage";
import { Button } from "@/components/ui/button";

const HIGHLIGHTS = [
  "All four modules in one place",
  "18 IELTS question types",
  "Academic and General Training",
] as const;

/**
 * Landing hero. Server Component; the headline is plain text so it is the LCP element and is
 * never hidden by an entrance animation. Only the decorative stage animates.
 */
export function Hero() {
  return (
    <section aria-labelledby="hero-heading" className="relative isolate overflow-x-clip border-b">
      <div aria-hidden="true" className="hero-backdrop absolute inset-0 -z-10" />
      <div aria-hidden="true" className="hero-grid absolute inset-0 -z-10" />
      <div className="mx-auto grid max-w-[var(--container-wide)] grid-cols-1 items-center gap-10 px-4 pt-12 pb-16 sm:px-6 sm:pt-16 lg:grid-cols-12 lg:gap-8 lg:px-8 lg:pt-20 lg:pb-24">
        <div className="flex min-w-0 flex-col items-start gap-6 lg:col-span-5">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground shadow-elevation-1 backdrop-blur">
            <span aria-hidden="true" className="size-1.5 rounded-full bg-brand-accent" />
            Listening · Reading · Writing · Speaking
          </p>
          <h1
            id="hero-heading"
            className="font-heading text-4xl leading-[1.08] font-bold tracking-[-0.03em] text-balance sm:text-5xl lg:text-[3.5rem]"
          >
            Prepare smarter.
            <br />
            <span className="text-brand-gradient">Achieve higher.</span>
          </h1>
          <p className="max-w-xl text-lg leading-relaxed text-pretty text-muted-foreground">
            Practise every part of the IELTS test in focused, exam-style layouts, with instant
            answer checking, clear explanations and progress you can follow.
          </p>
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row">
            <Button asChild className="h-11 px-5 text-[0.9375rem] shadow-elevation-2">
              <Link href="/practice">
                Start practising
                <ArrowRightIcon aria-hidden="true" data-icon="inline-end" />
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-11 px-5 text-[0.9375rem]">
              <Link href="/library">Browse the library</Link>
            </Button>
          </div>
          <ul className="flex flex-col gap-2 pt-2 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:gap-x-5">
            {HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-center gap-1.5">
                <CheckIcon aria-hidden="true" className="size-4 text-success" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0 lg:col-span-7">
          <HeroStage />
        </div>
      </div>
    </section>
  );
}
