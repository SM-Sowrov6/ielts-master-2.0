"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { makeQueryClient } from "@/lib/query/query-client";

/** App-wide client providers: theme (light/dark/system), server-state cache, toasts. */
export function Providers({ children }: { children: ReactNode }) {
  // One QueryClient per browser session (never shared between server requests).
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
