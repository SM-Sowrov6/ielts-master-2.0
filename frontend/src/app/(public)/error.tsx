"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/patterns/states";
import { Button } from "@/components/ui/button";

// Route-segment error boundary. Shows a generic message; details go to the console (Sentry later).
export default function SegmentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <ErrorState
      title="Something went wrong"
      description="This page could not be displayed. Please try again."
      action={<Button onClick={reset}>Try again</Button>}
    />
  );
}
