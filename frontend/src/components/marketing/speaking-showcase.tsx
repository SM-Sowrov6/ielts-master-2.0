import { ArrowRightIcon, MicIcon } from "lucide-react";
import Link from "next/link";

import { DecorativePreview } from "@/components/marketing/product-window";
import { SpeakingDemo } from "@/components/marketing/speaking-demo";
import { Button } from "@/components/ui/button";

/**
 * Module 04 · Speaking, flagship showcase: an introduction above an immersive CSS-3D AI speaking
 * scene (AI partner avatar, live conversation panel, voice waveforms, studio microphone) running
 * a synchronised sample exchange. The voice partner is not built yet, so the CTA is marked
 * "coming soon" and the scene is labelled as a sample.
 */
export function SpeakingShowcase() {
  return (
    <section
      id="speaking"
      aria-labelledby="speaking-heading"
      data-visual-side="full"
      className="sx-section relative overflow-x-clip border-b"
    >
      <div className="mx-auto max-w-[var(--container-wide)] px-4 pt-20 pb-24 sm:px-6 lg:px-8 lg:pt-28 lg:pb-28">
        <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-semibold tracking-[0.12em] text-primary uppercase shadow-elevation-1">
            <span
              aria-hidden="true"
              className="grid size-5 place-items-center rounded-full bg-accent text-accent-foreground"
            >
              <MicIcon className="size-3" />
            </span>
            Module 04 · Speaking
          </p>
          <h3
            id="speaking-heading"
            className="mt-5 font-heading text-4xl leading-[1.05] font-bold tracking-[-0.03em] text-balance sm:text-5xl lg:text-[3.5rem]"
          >
            Speak Naturally. <span className="text-brand-gradient">Speak Confidently.</span>
          </h3>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
            Build your speaking confidence with an intelligent AI speaking partner. Practise real
            IELTS-style conversations, improve your fluency, and express yourself naturally.
          </p>
          <Button
            asChild
            className="group mt-8 h-11 px-5 text-[0.9375rem] shadow-elevation-2 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-elevation-float"
          >
            <Link href="/speaking">
              Explore Speaking
              <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </Button>
        </div>

        <div className="relative mt-12 lg:mt-14">
          <p className="sr-only">
            Illustration: an AI speaking partner and a studio microphone. The partner asks a sample
            question about your hometown while a blue voice waveform moves, then the microphone
            shows Your Turn and the answer appears word by word with a green waveform.
          </p>
          <DecorativePreview className="sx-stage sx-reveal">
            <SpeakingDemo />
          </DecorativePreview>
        </div>
      </div>
    </section>
  );
}
