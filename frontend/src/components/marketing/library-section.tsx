import {
  BookOpenTextIcon,
  FileTextIcon,
  GraduationCapIcon,
  HeadphonesIcon,
  LanguagesIcon,
  ListChecksIcon,
  MicIcon,
  PenLineIcon,
  type LucideIcon,
} from "lucide-react";
import type { CSSProperties } from "react";

import { DecorativePreview } from "@/components/marketing/product-window";
import { SectionHeader } from "@/components/marketing/section-header";
import { SoonCta } from "@/components/marketing/soon-cta";

/** Original, generic sample covers (no real titles, publishers or cover designs). */
const BOOKS: readonly {
  category: string;
  title: string;
  icon: LucideIcon;
  tone: string;
  ry: number;
  z: number;
}[] = [
  {
    category: "Listening Practice",
    title: "Listening Practice Tests",
    icon: HeadphonesIcon,
    tone: "sky",
    ry: 26,
    z: 0,
  },
  {
    category: "Reading Practice",
    title: "Reading Skills and Strategies",
    icon: BookOpenTextIcon,
    tone: "indigo",
    ry: 16,
    z: 30,
  },
  {
    category: "IELTS Preparation",
    title: "Complete IELTS Preparation",
    icon: GraduationCapIcon,
    tone: "blue",
    ry: 0,
    z: 70,
  },
  {
    category: "Writing Guides",
    title: "Writing Task 1 and 2 Guide",
    icon: PenLineIcon,
    tone: "emerald",
    ry: -10,
    z: 50,
  },
  {
    category: "Speaking Resources",
    title: "Speaking Topics and Practice",
    icon: MicIcon,
    tone: "amber",
    ry: -18,
    z: 25,
  },
  {
    category: "Vocabulary Builder",
    title: "Academic Vocabulary Builder",
    icon: LanguagesIcon,
    tone: "violet",
    ry: -28,
    z: 0,
  },
];

const CARDS = [
  { icon: LanguagesIcon, title: "Vocabulary list", meta: "Environment · 40 words", tone: "violet" },
  {
    icon: ListChecksIcon,
    title: "Practice set",
    meta: "Matching headings · 12 questions",
    tone: "indigo",
  },
  { icon: FileTextIcon, title: "Study guide", meta: "Task 2 essay structure", tone: "emerald" },
] as const;

/**
 * L4 · Library (FR-LB): a centred introduction above a 3D digital library — six original sample
 * covers standing on a glass shelf, floating resource cards and the category labels. Covers and
 * cards are samples, not real publications. CSS 3D only.
 */
export function LibrarySection() {
  return (
    <section
      id="library"
      aria-labelledby="library-heading"
      className="relative overflow-x-clip px-4 py-20 sm:px-6 lg:px-8 lg:py-28"
    >
      <div className="mx-auto max-w-[var(--container-wide)]">
        <div className="flex flex-col items-center">
          <SectionHeader
            id="library-heading"
            eyebrow="Learn smarter"
            title="Everything You Need to Prepare, All in One Place."
          >
            Explore a growing collection of IELTS learning materials, practice resources, vocabulary
            guides, and study books to support your preparation journey.
          </SectionHeader>
          <SoonCta href="/library" label="Explore Library" className="mt-8" />
        </div>

        <div className="relative mt-14 lg:mt-16">
          <div aria-hidden="true" className="lb-ambient absolute -inset-x-4 -inset-y-10 -z-10" />
          <p className="sr-only">
            Illustration: a digital library with six sample IELTS study books for preparation,
            Listening, Reading, Writing, Speaking and vocabulary, standing on a glass shelf next to
            sample resource cards. The covers shown here are samples.
          </p>
          <DecorativePreview className="lb-stage">
            <div className="lb-scene">
              <div className="lb-shelf-row">
                {BOOKS.map((book, i) => (
                  <Book key={book.title} {...book} index={i} />
                ))}
              </div>
              <div className="lb-shelf" />
              {CARDS.map((card, i) => {
                const Icon = card.icon;
                return (
                  <div
                    key={card.title}
                    className={`lb-card lb-card-${i + 1}`}
                    data-tone={card.tone}
                  >
                    <span className="lb-card-icon">
                      <Icon className="size-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold">{card.title}</span>
                      <span className="block text-xs text-muted-foreground">{card.meta}</span>
                    </span>
                    <span className="ml-auto rounded-full bg-muted px-1.5 py-px text-[0.625rem] font-medium text-muted-foreground">
                      Sample
                    </span>
                  </div>
                );
              })}
            </div>
          </DecorativePreview>
          <ul className="mt-10 flex flex-wrap justify-center gap-2 text-sm">
            {BOOKS.map((book) => (
              <li key={book.category} className="lb-chip" data-tone={book.tone}>
                <span aria-hidden="true" />
                {book.category}
              </li>
            ))}
          </ul>
          <p className="mt-4 text-center text-xs text-muted-foreground">
            The covers shown here are samples. The library is being built and opens soon.
          </p>
        </div>
      </div>
    </section>
  );
}

function Book({
  category,
  title,
  icon: Icon,
  tone,
  ry,
  z,
  index,
}: (typeof BOOKS)[number] & { index: number }) {
  return (
    <div
      className="lb-book"
      data-tone={tone}
      style={
        {
          "--ry": `${ry}deg`,
          "--z": `${z}px`,
          "--delay": `${-index * 0.9}s`,
        } as CSSProperties
      }
    >
      <div className="lb-book-body">
        <span className="lb-face lb-pages" />
        <span className="lb-face lb-top" />
        <span className="lb-face lb-spine">
          <span>{category}</span>
        </span>
        <span className="lb-face lb-cover">
          <span className="lb-cover-pattern" />
          <span className="lb-cover-series">IELTS MASTER</span>
          <span className="lb-cover-icon">
            <Icon />
          </span>
          <span className="lb-cover-title">{title}</span>
          <span className="lb-cover-meta">{category}</span>
        </span>
      </div>
    </div>
  );
}
