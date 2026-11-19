import type { Metadata } from "next";

import { FinalCtaSection, HowItWorksSection } from "@/components/marketing/closing-sections";
import { CoachSection } from "@/components/marketing/coach-section";
import { Hero } from "@/components/marketing/hero";
import { LibrarySection } from "@/components/marketing/library-section";
import { MockExamSection } from "@/components/marketing/mock-exam-section";
import { ModuleSections } from "@/components/marketing/modules";
import { ProgressSection } from "@/components/marketing/progress-section";
import { SkillMarquee } from "@/components/marketing/skill-marquee";

export const metadata: Metadata = {
  title: { absolute: "IELTS MASTER 2.0 · Prepare for all four IELTS skills" },
  description:
    "Structured IELTS preparation for Listening, Reading, Writing and Speaking in focused, exam-style layouts.",
};

/**
 * Landing page: hero (L2), the 3D skill marquee, the four modules (L3), then coach, mock exam, library, progress,
 * how it works and the final call to action (L4). No pricing until it is approved.
 */
export default function HomePage() {
  return (
    <>
      <Hero />
      <SkillMarquee />
      <ModuleSections />
      <CoachSection />
      <MockExamSection />
      <LibrarySection />
      <ProgressSection />
      <HowItWorksSection />
      <FinalCtaSection />
    </>
  );
}
