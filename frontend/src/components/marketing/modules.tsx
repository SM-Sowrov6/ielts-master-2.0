import { ListeningShowcase } from "@/components/marketing/listening-showcase";
import { ReadingShowcase } from "@/components/marketing/reading-showcase";
import { SpeakingShowcase } from "@/components/marketing/speaking-showcase";
import { WritingShowcase } from "@/components/marketing/writing-showcase";

/**
 * L3: the four IELTS modules, each a full-width flagship showcase. Copy follows the agreed
 * product requirements (docs/PROJECT_REQUIREMENTS.md: FR-RL, FR-WR, FR-SP). No affiliation,
 * endorsement, guarantee or usage claims.
 */
export function ModuleSections() {
  return (
    <section id="modules" aria-labelledby="modules-heading">
      <div className="mx-auto max-w-[var(--container-wide)] px-4 pt-20 pb-4 text-center sm:px-6 lg:px-8 lg:pt-28">
        <p className="text-xs font-semibold tracking-[0.14em] text-primary uppercase">
          The four skills
        </p>
        <h2
          id="modules-heading"
          className="mx-auto mt-3 max-w-2xl font-heading text-3xl font-bold tracking-[-0.02em] text-balance sm:text-4xl lg:text-[2.75rem]"
        >
          Everything the IELTS test asks of you, in one place
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
          Listening, Reading, Writing and Speaking each have their own focused workspace, built
          around the format of the real test.
        </p>
      </div>
      <ListeningShowcase />
      <ReadingShowcase />
      <WritingShowcase />
      <SpeakingShowcase />
    </section>
  );
}
