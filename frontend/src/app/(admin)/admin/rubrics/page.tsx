import type { Metadata } from "next";

import { RubricManager } from "@/components/admin/productive/rubric-manager";
import { StaffOnly } from "@/components/auth/gates";
import { PageHeader } from "@/components/patterns/page-header";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Assessment rubrics" };

export default async function RubricsPage({
  searchParams,
}: {
  searchParams: Promise<{ module?: string }>;
}) {
  const { module: requested } = await searchParams;
  const selected = requested === "speaking" ? "speaking" : "writing";
  const user = await requireStaff(`/admin/rubrics?module=${selected}`);
  return (
    <StaffOnly path={`/admin/rubrics?module=${selected}`}>
      <PageHeader
        title={`${selected === "writing" ? "Writing" : "Speaking"} assessment rubric`}
        description="Versioned criteria and band descriptors the AI evaluator marks against. Written in the platform's own words, reviewed by a second staff member and published like content."
      />
      <nav aria-label="Rubric module" className="mb-4 flex gap-2 text-sm">
        <a
          href="/admin/rubrics?module=writing"
          aria-current={selected === "writing" ? "page" : undefined}
          className="rounded-full border px-3 py-1 aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground"
        >
          Writing
        </a>
        <a
          href="/admin/rubrics?module=speaking"
          aria-current={selected === "speaking" ? "page" : undefined}
          className="rounded-full border px-3 py-1 aria-[current=page]:bg-primary aria-[current=page]:text-primary-foreground"
        >
          Speaking
        </a>
      </nav>
      {user && <RubricManager key={selected} user={user} module={selected} />}
    </StaffOnly>
  );
}
