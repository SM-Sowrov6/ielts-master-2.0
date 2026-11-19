import type { Metadata } from "next";

import { FocusShell } from "@/components/layout/focus-shell";
import { EmptyState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Exam room (layout preview)", robots: { index: false } };

/** Layout preview only. The examination engine is delivered in Phase 7. */
export default function Page() {
  return (
    <FocusShell
      title="Exam room (layout preview)"
      status={<span>Timer slot</span>}
      footer={
        <div className="flex justify-between gap-2">
          <Button variant="outline" disabled>
            Previous
          </Button>
          <Button disabled>Next</Button>
        </div>
      }
    >
      <EmptyState
        title="Layout preview"
        description="Distraction-free exam layout. Questions, the server-synced timer and answer saving arrive in Phase 7."
      />
    </FocusShell>
  );
}
