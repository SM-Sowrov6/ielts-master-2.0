import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";

import { soonLabel } from "@/components/layout/soon-badge";
import { CoachDemo } from "@/components/marketing/coach-demo";
import { DecorativePreview } from "@/components/marketing/product-window";
import { SectionHeader } from "@/components/marketing/section-header";
import { Button } from "@/components/ui/button";

/**
 * L4 · AI Coach (FR-CO): an introduction above an immersive CSS-3D coaching workspace — the
 * IELTS MASTER coach robot, a coaching conversation, a sample feedback card and recommendation
 * cards — running one synchronised sample exchange. The coach is not built yet: the CTA is marked
 * "coming soon" and every figure is labelled as a sample.
 */
export function CoachSection() {
  return (
    <section
      id="coach"
      aria-labelledby="coach-heading"
      className="cx-section relative overflow-x-clip px-4 py-20 sm:px-6 lg:px-8 lg:py-28"
    >
      <div className="mx-auto grid max-w-[var(--container-wide)] items-center gap-12 lg:grid-cols-[minmax(0,0.78fr)_minmax(0,1.45fr)] lg:gap-14">
        <div>
          <SectionHeader
            id="coach-heading"
            eyebrow="Your personal AI mentor"
            title="Meet Your AI IELTS Coach."
            align="left"
          >
            Get personalized guidance, instant feedback, and smart recommendations to improve your
            IELTS skills. Your AI coach understands your learning journey and helps you move closer
            to your target band score.
          </SectionHeader>
          <div className="mt-8 flex">
            <Button
              asChild
              className="group h-11 px-5 text-[0.9375rem] shadow-elevation-2 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-elevation-float"
            >
              <Link href="/coach" aria-label={soonLabel("Explore AI Coach")}>
                Explore AI Coach
                <span className="rounded-full bg-primary-foreground/20 px-1.5 py-px text-[0.625rem] font-semibold tracking-wide uppercase">
                  Soon
                </span>
                <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            </Button>
          </div>
        </div>

        <div className="relative min-w-0">
          <div aria-hidden="true" className="cx-ambient absolute -inset-x-6 -inset-y-10 -z-10" />
          <p className="sr-only">
            Illustration: the AI coach robot next to a coaching chat. A student asks for help with
            Writing Task 2, the coach suggests working on essay structure and clearer topic
            sentences, a sample feedback card summarises the four Writing criteria without scores,
            and three recommended practice topics appear.
          </p>
          <DecorativePreview className="cx-stage">
            <CoachDemo />
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
