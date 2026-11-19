import type { Metadata } from "next";

import { FocusShell } from "@/components/layout/focus-shell";
import { EmptyState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Speaking room (layout preview)",
  robots: { index: false },
};

/** Layout preview only. The real-time speaking partner is delivered in Phase 10. */
export default function Page() {
  return (
    <FocusShell
      title="Speaking room (layout preview)"
      status={<span>Session status slot</span>}
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
        description="Distraction-free speaking layout. The live voice session arrives in Phase 10."
      />
    </FocusShell>
  );
}
