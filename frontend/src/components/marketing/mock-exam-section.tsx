import { MockExamDemo } from "@/components/marketing/mock-exam-demo";
import { DecorativePreview } from "@/components/marketing/product-window";
import { SectionHeader } from "@/components/marketing/section-header";
import { SoonCta } from "@/components/marketing/soon-cta";

/**
 * L4 · Mock exam (FR-MT): an exam-software workspace (section tabs, timer, passage, questions,
 * question map) on the left, the introduction on the right. Illustrative only; the mock exams
 * are not available yet, so the CTA is marked "coming soon".
 */
export function MockExamSection() {
  return (
    <section
      id="mock-exam"
      aria-labelledby="mock-exam-heading"
      className="relative overflow-x-clip border-y bg-surface/70 px-4 py-20 sm:px-6 lg:px-8 lg:py-28"
    >
      <div className="mx-auto grid max-w-[var(--container-wide)] items-center gap-12 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,0.8fr)] lg:gap-14">
        <div className="lg:order-2">
          <SectionHeader
            id="mock-exam-heading"
            eyebrow="Real exam experience"
            title="Experience the Real IELTS Exam Before Test Day."
            align="left"
          >
            Prepare with realistic IELTS mock tests designed to help you become familiar with the
            exam format, manage your time, and understand your performance.
          </SectionHeader>
          <SoonCta href="/mock-tests" label="Explore Mock Exams" className="mt-8" />
        </div>
        <div className="relative min-w-0 lg:order-1">
          <div aria-hidden="true" className="mk-ambient absolute -inset-8 -z-10" />
          <p className="sr-only">
            Illustration: a computer-based IELTS mock exam. The Reading section is open with a
            passage about rooftop gardens; questions 14 to 16 are answered one after another while
            the timer counts down and the question map fills in.
          </p>
          <DecorativePreview className="mk-stage">
            <MockExamDemo />
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
