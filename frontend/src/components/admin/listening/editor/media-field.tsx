"use client";

import { useQuery } from "@tanstack/react-query";
import { FileAudioIcon, ImageIcon, LoaderCircleIcon, UploadIcon, XIcon } from "lucide-react";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { fetchMediaUrl, type Asset } from "@/lib/admin/listening-api";
import { AUDIO_TYPES, IMAGE_TYPES, uploadMedia, type UploadPhase } from "@/lib/admin/upload";
import { messageFor } from "@/lib/auth/api";
import { queryKeys } from "@/lib/query/keys";

const PHASE_LABEL: Record<UploadPhase, string> = {
  hashing: "Preparing file…",
  uploading: "Uploading to media storage…",
  verifying: "Verifying the stored file…",
};

function size(bytes: number | null | undefined): string {
  if (!bytes) return "";
  return bytes > 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.ceil(bytes / 1024)} KB`;
}

function Player({ asset, kind }: { asset: Asset; kind: "audio" | "image" }) {
  // Presigned URLs live 5 minutes; refetch before they expire.
  const url = useQuery({
    queryKey: queryKeys.listening.media(asset.id),
    queryFn: () => fetchMediaUrl(asset.id),
    enabled: asset.status === "ready",
    staleTime: 4 * 60_000,
    refetchInterval: 4 * 60_000,
  });
  if (asset.status !== "ready") {
    return (
      <p className="text-sm text-destructive">This file is {asset.status} and cannot be played.</p>
    );
  }
  if (url.isPending) return <p className="text-sm text-muted-foreground">Loading preview…</p>;
  if (url.isError) return <p className="text-sm text-destructive">{messageFor(url.error)}</p>;
  return kind === "audio" ? (
    <audio controls preload="metadata" src={url.data.url} className="w-full">
      Your browser cannot play this audio.
    </audio>
  ) : (
    // eslint-disable-next-line @next/next/no-img-element -- short-lived presigned URL, not optimisable
    <img
      src={url.data.url}
      alt="Uploaded question image"
      className="max-h-64 rounded-md border object-contain"
    />
  );
}

/**
 * Upload / preview / replace one media asset. The parent receives the new asset only after the
 * server has verified the stored file; failures are shown and nothing is attached.
 */
export function MediaField({
  label,
  kind,
  testId,
  assetId,
  assets,
  readOnly,
  onUploaded,
  onRemove,
}: {
  label: string;
  kind: "audio" | "image";
  testId: string;
  assetId: string | null | undefined;
  assets: ReadonlyMap<string, Asset>;
  readOnly: boolean;
  onUploaded: (asset: Asset) => void;
  onRemove?: () => void;
}) {
  const inputId = useId();
  const statusId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<UploadPhase | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const asset = assetId ? assets.get(assetId) : undefined;
  const Icon = kind === "audio" ? FileAudioIcon : ImageIcon;
  const accept = Object.keys(kind === "audio" ? AUDIO_TYPES : IMAGE_TYPES).join(",");

  async function handle(file: File) {
    setError(null);
    setDone(null);
    setProgress(0);
    try {
      const uploaded = await uploadMedia(file, {
        testId,
        kind,
        onPhase: setPhase,
        onProgress: setProgress,
      });
      onUploaded(uploaded);
      setDone(`${file.name} uploaded and verified. Save the draft to keep this change.`);
    } catch (e) {
      setError(e instanceof Error && !("status" in e) ? e.message : messageFor(e));
    } finally {
      setPhase(null);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-2 rounded-lg border bg-background/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
          {label}
        </p>
        {!readOnly && (
          <div className="flex gap-2">
            <input
              ref={input}
              id={inputId}
              type="file"
              accept={accept}
              className="sr-only"
              tabIndex={-1}
              aria-label={`Choose a file for ${label}`}
              aria-describedby={statusId}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handle(file);
              }}
              disabled={phase !== null}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={phase !== null}
              onClick={() => input.current?.click()}
            >
              <UploadIcon aria-hidden="true" />
              {assetId ? "Replace" : "Upload"}
            </Button>
            {assetId && onRemove && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onRemove}
                disabled={phase !== null}
              >
                <XIcon aria-hidden="true" />
                Remove
              </Button>
            )}
          </div>
        )}
      </div>
      <div id={statusId} aria-live="polite" className="space-y-2 text-sm">
        {phase && (
          <div className="space-y-1">
            <p className="flex items-center gap-2 text-muted-foreground">
              <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" />
              {PHASE_LABEL[phase]}
              {phase === "uploading" && ` ${Math.round(progress * 100)}%`}
            </p>
            {phase === "uploading" && (
              <div
                role="progressbar"
                aria-label="Upload progress"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(progress * 100)}
                className="h-2 overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full bg-primary transition-[width]"
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
            )}
          </div>
        )}
        {error && (
          <p role="alert" className="text-destructive">
            Upload failed: {error} Nothing was attached.
          </p>
        )}
        {done && <p className="text-success">{done}</p>}
        {!assetId && !phase && (
          <p className="text-muted-foreground">
            No {kind === "audio" ? "audio" : "image"} yet. Allowed:{" "}
            {[...new Set(Object.values(kind === "audio" ? AUDIO_TYPES : IMAGE_TYPES))].join(", ")}.
          </p>
        )}
      </div>
      {assetId && (
        <div className="space-y-2">
          {asset ? (
            <>
              <p className="text-xs text-muted-foreground">
                {asset.original_filename ?? "Uploaded file"}{" "}
                {size(asset.size_bytes) && `· ${size(asset.size_bytes)}`}
              </p>
              <Player asset={asset} kind={kind} />
            </>
          ) : (
            <p className="text-xs text-muted-foreground">File reference {assetId}</p>
          )}
        </div>
      )}
    </div>
  );
}
