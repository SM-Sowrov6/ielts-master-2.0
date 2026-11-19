import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Gallery } from "@/app/(public)/design-system/gallery";
import { PageHeader } from "@/components/patterns/page-header";

export const metadata: Metadata = { title: "Design system", robots: { index: false } };

/** Development-only component gallery for review and accessibility checks. */
export default function DesignSystemPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return (
    <>
      <PageHeader
        title="Design system"
        description="Tokens, primitives and patterns (docs/FRONTEND_DESIGN_SYSTEM.md). Development builds only."
      />
      <Gallery />
    </>
  );
}
