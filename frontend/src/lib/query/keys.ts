/**
 * Query-key factory convention (docs/FRONTEND_DESIGN_SYSTEM.md §6).
 *
 * Each feature owns one entry: `<domain>.all` is the invalidation root, and narrower keys extend
 * it, so `queryClient.invalidateQueries({ queryKey: queryKeys.<domain>.all })` clears everything
 * for that domain. Keys are tuples of serialisable values only.
 *
 * Feature modules add their own entries when they are built (e.g. `library`, `attempts`).
 */
export const queryKeys = {
  auth: {
    all: ["auth"] as const,
    me: () => [...queryKeys.auth.all, "me"] as const,
    registrationPolicy: () => [...queryKeys.auth.all, "registration-policy"] as const,
  },
  listening: {
    all: ["admin", "listening"] as const,
    overview: () => [...queryKeys.listening.all, "overview"] as const,
    list: (query: Record<string, string | number | undefined>) =>
      [...queryKeys.listening.all, "list", query] as const,
    document: (versionId: string) => [...queryKeys.listening.all, "document", versionId] as const,
    validation: (versionId: string) =>
      [...queryKeys.listening.all, "validation", versionId] as const,
    preview: (versionId: string) => [...queryKeys.listening.all, "preview", versionId] as const,
    catalog: () => [...queryKeys.listening.all, "catalog"] as const,
    questionTypes: () => [...queryKeys.listening.all, "question-types"] as const,
    media: (assetId: string) => [...queryKeys.listening.all, "media", assetId] as const,
  },
  system: {
    all: ["system"] as const,
    readiness: () => [...queryKeys.system.all, "readiness"] as const,
  },
} as const;
