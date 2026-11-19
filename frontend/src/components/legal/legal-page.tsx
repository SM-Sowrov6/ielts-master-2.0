import type { ReactNode } from "react";

/**
 * Legal documents (decision D-17). The text is a DRAFT until the owner approves it; then set
 * `LEGAL_APPROVED = true` here and LEGAL_TERMS_VERSION / LEGAL_PRIVACY_VERSION = LEGAL_VERSION on
 * the server, which opens public registration. Changing the text later = new version.
 */
export const LEGAL_VERSION = "2026-11-20";
export const LEGAL_APPROVED = true;
/** Contact address shown in the documents (Cloudflare Email Routing → owner's inbox). */
export const LEGAL_CONTACT = "support@ieltsmaster.site";

export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <article className="mx-auto w-full max-w-3xl px-4 py-12 sm:py-16">
      {!LEGAL_APPROVED && (
        <p
          role="note"
          className="mb-6 rounded-xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm"
        >
          Draft — this document is awaiting approval and is not yet in effect.
        </p>
      )}
      <h1 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Version {LEGAL_VERSION} · Last updated 20 November 2026
      </p>
      <div className="mt-8 space-y-6 leading-relaxed [&_h2]:mt-10 [&_h2]:font-heading [&_h2]:text-xl [&_h2]:font-semibold [&_li]:mt-1.5 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-6">
        {children}
      </div>
    </article>
  );
}
