"use client";

import { useSyncExternalStore } from "react";

/**
 * Small helpers shared by the choreographed landing demos (timers only, no animation library).
 */

/** Position of `el` in the layout coordinates of `root` (unaffected by 3D transforms). */
export function localPoint(el: HTMLElement, root: HTMLElement, fx = 0, fy = 0.5) {
  let x = 0;
  let y = 0;
  let node: HTMLElement | null = el;
  while (node && node !== root) {
    x += node.offsetLeft;
    y += node.offsetTop;
    node = node.offsetParent as HTMLElement | null;
  }
  return { x: x + el.offsetWidth * fx, y: y + el.offsetHeight * fy };
}

/** Thrown by a demo's `wait` once the demo is torn down, to unwind the running sequence. */
export class Cancelled extends Error {}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** True when the user asks for reduced motion (server render: false). */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

/**
 * Runs `sequence` in a loop while `target` is on screen, until the returned cleanup is called.
 * `wait(ms)` rejects with `Cancelled` after cleanup, so the sequence stops at its next step.
 */
export function loopWhileVisible(
  target: Element | null,
  sequence: (wait: (ms: number) => Promise<void>) => Promise<void>,
): () => void {
  let cancelled = false;
  let onScreen = typeof IntersectionObserver === "undefined";
  let wake: (() => void) | null = null;
  const timers = new Set<number>();

  const wait = (ms: number) =>
    new Promise<void>((resolve, reject) => {
      const id = window.setTimeout(() => {
        timers.delete(id);
        if (cancelled) reject(new Cancelled());
        else resolve();
      }, ms);
      timers.add(id);
    });
  const whenOnScreen = () =>
    onScreen
      ? Promise.resolve()
      : new Promise<void>((resolve) => {
          wake = resolve;
        });

  const observer =
    typeof IntersectionObserver === "undefined"
      ? null
      : new IntersectionObserver(
          ([entry]) => {
            onScreen = entry?.isIntersecting ?? false;
            if (onScreen && wake) {
              wake();
              wake = null;
            }
          },
          { threshold: 0.25 },
        );
  if (observer && target) observer.observe(target);

  (async () => {
    while (!cancelled) {
      await whenOnScreen();
      if (cancelled) break;
      await sequence(wait);
    }
  })().catch(() => undefined);

  return () => {
    cancelled = true;
    for (const id of timers) window.clearTimeout(id);
    observer?.disconnect();
  };
}
