"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { fetchMe, signOut, type Me } from "@/lib/auth/api";
import { queryKeys } from "@/lib/query/keys";

/**
 * The signed-in user for UI purposes (menus, greetings). Never an authorization decision:
 * the backend re-checks the session and permissions on every request.
 */
export function useCurrentUser() {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchMe,
    staleTime: 30_000,
    retry: false,
  });
}

export function useSetCurrentUser() {
  const queryClient = useQueryClient();
  return useCallback(
    (user: Me | null) => queryClient.setQueryData(queryKeys.auth.me(), user),
    [queryClient],
  );
}

/** Sign out, clear cached user data and refresh server components. */
export function useSignOut() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useCallback(async () => {
    try {
      await signOut();
    } finally {
      queryClient.clear();
      queryClient.setQueryData(queryKeys.auth.me(), null);
      router.push("/");
      router.refresh();
    }
  }, [queryClient, router]);
}
