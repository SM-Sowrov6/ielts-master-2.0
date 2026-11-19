"use client";

import { cn } from "@/lib/utils";
import { DIFFICULTY, TONE, type Examiner } from "@/lib/practice/room-api";

export function ExaminerAvatar({
  examiner,
  size = "md",
  speaking = false,
}: {
  examiner: Pick<Examiner, "name" | "avatar_tone">;
  size?: "sm" | "md" | "lg" | "xl";
  speaking?: boolean;
}) {
  const dims = {
    sm: "size-9 text-sm",
    md: "size-14 text-lg",
    lg: "size-20 text-2xl",
    xl: "size-32 text-4xl",
  }[size];
  return (
    <span className="relative inline-flex shrink-0">
      {speaking && (
        <span
          className="absolute -inset-2 animate-ping rounded-full bg-primary/20 motion-reduce:hidden"
          aria-hidden="true"
        />
      )}
      <span
        className={cn(
          "relative inline-flex items-center justify-center rounded-full bg-gradient-to-br font-heading font-semibold shadow-elevation-2 ring-4 ring-background",
          TONE[examiner.avatar_tone] ?? TONE.primary,
          dims,
        )}
        aria-hidden="true"
      >
        {examiner.name.slice(0, 1)}
      </span>
    </span>
  );
}

export function ExaminerCard({
  examiner,
  selected,
  onSelect,
}: {
  examiner: Examiner;
  selected?: boolean;
  onSelect?: () => void;
}) {
  return (
    <article
      className={cn(
        "flex flex-col gap-4 rounded-2xl border bg-card p-5 shadow-elevation-1 transition-shadow hover:shadow-elevation-2",
        selected && "border-primary ring-2 ring-primary/30",
      )}
    >
      <div className="flex items-center gap-4">
        <ExaminerAvatar examiner={examiner} />
        <div className="min-w-0">
          <h3 className="font-heading text-lg font-semibold">{examiner.name}</h3>
          <p className="text-sm text-muted-foreground">{examiner.title}</p>
        </div>
        <span className="ml-auto rounded-full border px-2.5 py-0.5 text-xs font-medium">
          {DIFFICULTY[examiner.difficulty]}
        </span>
      </div>
      <p className="text-sm">{examiner.personality}</p>
      <dl className="space-y-1 text-xs text-muted-foreground">
        <div className="flex gap-1">
          <dt className="font-medium text-foreground">Style:</dt>
          <dd>{examiner.speaking_style}</dd>
        </div>
        <div className="flex gap-1">
          <dt className="font-medium text-foreground">Voice:</dt>
          <dd>
            {examiner.voice_configured
              ? (examiner.accent ?? "Configured")
              : `${examiner.accent ? `${examiner.accent} · ` : ""}voice not connected yet`}
          </dd>
        </div>
      </dl>
      {onSelect && (
        <button
          type="button"
          onClick={onSelect}
          aria-pressed={selected}
          className={cn(
            "mt-auto inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            selected ? "bg-primary text-primary-foreground" : "border bg-background hover:bg-muted",
          )}
        >
          {selected ? `${examiner.name} selected` : `Select ${examiner.name}`}
        </button>
      )}
    </article>
  );
}
