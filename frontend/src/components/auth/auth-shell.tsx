import { CheckIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Brand } from "@/components/layout/brand";
import { SkipLink } from "@/components/layout/skip-link";
import { ThemeToggle } from "@/components/layout/theme-toggle";

const POINTS = [
  "Listening, Reading, Writing and Speaking in one place",
  "Exam-style layouts for all 18 IELTS question types",
  "Your progress, saved securely to your account",
] as const;

/**
 * Layout for sign-in, registration and account-recovery pages: a focused form column and, from
 * `lg`, a brand panel. Server Component. Uses the approved brand tokens (Royal Blue, Emerald).
 */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
      <SkipLink />
      <div className="flex min-w-0 flex-col">
        <header className="mx-auto flex h-16 w-full max-w-xl items-center justify-between px-4 sm:px-8 lg:max-w-none">
          <Brand mark />
          <ThemeToggle />
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className="flex flex-1 items-start justify-center px-4 py-8 focus:outline-none sm:items-center sm:px-8 sm:py-12"
        >
          <div className="w-full max-w-[26rem]">{children}</div>
        </main>
        <footer className="px-4 pb-6 text-center text-xs text-muted-foreground sm:px-8">
          <p>AI-generated band scores are estimates and are not official IELTS results.</p>
          <p className="mt-1">
            <Link href="/" className="rounded-sm underline-offset-4 hover:underline">
              Back to home
            </Link>
          </p>
        </footer>
      </div>
      <aside
        aria-label="About IELTS MASTER"
        className="relative isolate hidden overflow-hidden bg-primary text-primary-foreground lg:flex lg:flex-col lg:justify-center lg:px-14 xl:px-20"
      >
        <div aria-hidden="true" className="auth-panel-glow absolute inset-0 -z-10" />
        <div aria-hidden="true" className="auth-panel-grid absolute inset-0 -z-10" />
        <p className="font-heading text-3xl leading-tight font-bold tracking-tight xl:text-4xl">
          Prepare smarter.
          <br />
          Achieve higher.
        </p>
        <ul className="mt-8 space-y-4 text-[0.9375rem]">
          {POINTS.map((point) => (
            <li key={point} className="flex items-start gap-3">
              <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-primary-foreground/15">
                <CheckIcon className="size-3.5" aria-hidden="true" />
              </span>
              {point}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
