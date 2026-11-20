"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useState, type ReactNode } from "react";

import { FloatingAssistant } from "@/components/assistant/floating-assistant";
import { Toaster } from "@/components/ui/sonner";
import { makeQueryClient } from "@/lib/query/query-client";

/**
 * App-wide client providers: theme (light/dark/system), server-state cache, toasts, and the
 * floating site assistant (it hides itself on exam, Speaking-session and staff routes).
 */
export function Providers({ children }: { children: ReactNode }) {
  // One QueryClient per browser session (never shared between server requests).
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        {children}
        <FloatingAssistant />
        {/* Raised so toasts never cover the assistant launcher (bottom-right). */}
        <Toaster closeButton offset={{ bottom: "6rem" }} mobileOffset={{ bottom: "5.5rem" }} />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
