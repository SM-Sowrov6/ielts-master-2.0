"use client";

import { createContext, useContext, type ReactNode } from "react";

/** Objective modules sharing the admin test editor (backend: content.authoring.OBJECTIVE). */
/** Content modules sharing the admin catalogue, workflow and editor shell. */
export type AdminModule = "listening" | "reading" | "writing" | "speaking";
export type ObjectiveModule = "listening" | "reading";

export const MODULE_INFO: Record<
  AdminModule,
  {
    title: string;
    base: string;
    sectionNoun: string;
    sectionCount: number;
    audio: boolean;
    passages: boolean;
    productive: boolean;
    minutes: number;
  }
> = {
  listening: {
    title: "Listening",
    base: "/admin/listening",
    sectionNoun: "Section",
    sectionCount: 4,
    audio: true,
    passages: false,
    productive: false,
    minutes: 30,
  },
  reading: {
    title: "Reading",
    base: "/admin/reading",
    sectionNoun: "Passage",
    sectionCount: 3,
    audio: false,
    passages: true,
    productive: false,
    minutes: 60,
  },
  writing: {
    title: "Writing",
    base: "/admin/writing",
    sectionNoun: "Task",
    sectionCount: 2,
    audio: false,
    passages: false,
    productive: true,
    minutes: 60,
  },
  speaking: {
    title: "Speaking",
    base: "/admin/speaking",
    sectionNoun: "Part",
    sectionCount: 3,
    audio: false,
    passages: false,
    productive: true,
    minutes: 14,
  },
};

const ModuleContext = createContext<AdminModule>("listening");

export function AdminModuleProvider({
  module,
  children,
}: {
  module: AdminModule;
  children: ReactNode;
}) {
  return <ModuleContext.Provider value={module}>{children}</ModuleContext.Provider>;
}

export function useAdminModule(): AdminModule {
  return useContext(ModuleContext);
}

export function useModuleInfo() {
  const current = useAdminModule();
  return { module: current, ...MODULE_INFO[current] };
}
