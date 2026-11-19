"use client";

import { createContext, useContext, type ReactNode } from "react";

/** Candidate objective modules sharing the attempt/exam UI (backend: exams TEMPLATES). */
export type ExamModule = "listening" | "reading";

export const EXAM_MODULES: Record<
  ExamModule,
  { title: string; base: string; examBase: string; partNoun: string; blurb: string }
> = {
  listening: {
    title: "Listening",
    base: "/listening",
    examBase: "/exam/listening",
    partNoun: "Part",
    blurb:
      "Four recorded parts, 40 questions, real exam question types. Practise at your own pace or take it in exam mode with the official timing.",
  },
  reading: {
    title: "Reading",
    base: "/reading",
    examBase: "/exam/reading",
    partNoun: "Passage",
    blurb:
      "Three passages, 40 questions, every IELTS Reading question type. Practise at your own pace or take it in exam mode with the official 60 minutes.",
  },
};

const Ctx = createContext<ExamModule>("listening");

export function ExamModuleProvider({
  module,
  children,
}: {
  module: ExamModule;
  children: ReactNode;
}) {
  return <Ctx.Provider value={module}>{children}</Ctx.Provider>;
}

export function useExamModule() {
  const current = useContext(Ctx);
  return { module: current, ...EXAM_MODULES[current] };
}
