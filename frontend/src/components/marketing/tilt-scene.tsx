"use client";

import { useEffect, useRef, type ReactNode } from "react";

const clamp = (value: number) => Math.max(-1, Math.min(1, value));

/**
 * Pointer-driven tilt for the hero 3D scene. Writes `--tilt-x` / `--tilt-y` (-1…1) on its own
 * element; the CSS (`.hero-scene`) turns them into a few degrees of rotation.
 * Only active for a fine, hovering pointer and when reduced motion is NOT requested; touch
 * devices and reduced-motion users get the static composition. Children stay server-rendered.
 */
export function TiltScene({ children, className }: { children: ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const scene = ref.current;
    const area = scene?.closest("section") ?? scene?.parentElement;
    if (!scene || !area) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)");
    let frame = 0;

    const apply = (x: number, y: number) => {
      scene.style.setProperty("--tilt-x", x.toFixed(3));
      scene.style.setProperty("--tilt-y", y.toFixed(3));
    };
    const onMove = (event: PointerEvent) => {
      if (reduce.matches || !fine.matches) return;
      const rect = area.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const x = clamp(((event.clientX - rect.left) / rect.width) * 2 - 1);
      const y = clamp(((event.clientY - rect.top) / rect.height) * 2 - 1);
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => apply(x, y));
    };
    const onLeave = () => {
      cancelAnimationFrame(frame);
      apply(0, 0);
    };

    area.addEventListener("pointermove", onMove, { passive: true });
    area.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      area.removeEventListener("pointermove", onMove);
      area.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
