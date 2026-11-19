import { ConstructionIcon } from "lucide-react";

import type { NavItem } from "@/components/layout/nav-config";
import { PageHeader } from "@/components/patterns/page-header";
import { EmptyState } from "@/components/patterns/states";

/** Placeholder for shell routes whose feature is delivered in a later roadmap phase. */
export function ComingSoon({ item }: { item: NavItem }) {
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <EmptyState
        icon={ConstructionIcon}
        title="Not available yet"
        description={`This area is part of roadmap phase ${item.phase}. The layout and navigation are in place; the feature itself has not been built.`}
      />
    </>
  );
}
