import Link from "next/link";

import { SiteShell } from "@/components/layout/site-shell";
import { EmptyState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <SiteShell>
      <EmptyState
        title="Page not found"
        description="The page you are looking for does not exist or has moved."
        action={
          <Button asChild>
            <Link href="/">Go to the home page</Link>
          </Button>
        }
      />
    </SiteShell>
  );
}
