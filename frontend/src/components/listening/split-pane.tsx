"use client";

import { GripVerticalIcon } from "lucide-react";
import { useCallback, useRef, useState, type ReactNode } from "react";

const MIN = 25;
const MAX = 75;
const KEY = "reading-split";

function initial(): number {
  try {
    const v = Number(localStorage.getItem(KEY));
    return v >= MIN && v <= MAX ? v : 50;
  } catch {
    return 50;
  }
}

/**
 * Passage | questions layout of the computer-delivered test: two independently scrolling panes
 * and a divider that can be dragged (or moved with the arrow keys) to resize them. On small screens
 * the panes stack.
 */
export function SplitPane({ left, right }: { left: ReactNode; right: ReactNode }) {
  const [pct, setPct] = useState(initial);
  const box = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const set = useCallback((next: number) => {
    const v = Math.round(Math.min(MAX, Math.max(MIN, next)));
    setPct(v);
    try {
      localStorage.setItem(KEY, String(v));
    } catch {
      /* ignore */
    }
  }, []);

  const move = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect();
    if (rect && rect.width > 0) set(((clientX - rect.left) / rect.width) * 100);
  };

  return (
    <div
      ref={box}
      className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto lg:flex-row lg:gap-0 lg:overflow-hidden"
      style={{ ["--split" as string]: `${pct}%` }}
    >
      <div className="min-w-0 [scrollbar-width:thin] lg:h-full lg:w-[var(--split)] lg:shrink-0 lg:overflow-y-auto lg:pr-4">
        {left}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize passage and questions"
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        aria-valuenow={pct}
        tabIndex={0}
        title="Drag to resize · double-click to reset"
        className="group relative hidden w-3 shrink-0 cursor-col-resize touch-none items-center justify-center lg:flex focus-visible:outline-none"
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => dragging.current && move(e.clientX)}
        onPointerUp={(e) => {
          dragging.current = false;
          e.currentTarget.releasePointerCapture(e.pointerId);
        }}
        onDoubleClick={() => set(50)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") set(pct - 5);
          else if (e.key === "ArrowRight") set(pct + 5);
          else if (e.key === "Home") set(MIN);
          else if (e.key === "End") set(MAX);
          else return;
          e.preventDefault();
        }}
      >
        <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-primary group-focus-visible:bg-primary" />
        <span className="relative flex h-12 w-5 items-center justify-center rounded-md border bg-card shadow-elevation-1 transition-colors group-hover:border-primary group-focus-visible:border-primary group-focus-visible:ring-2 group-focus-visible:ring-ring">
          <GripVerticalIcon className="size-4 text-muted-foreground" aria-hidden="true" />
        </span>
      </div>
      <div className="min-w-0 flex-1 [scrollbar-width:thin] lg:h-full lg:overflow-y-auto lg:pl-4">
        {right}
      </div>
    </div>
  );
}
