/**
 * Media upload flow (docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §5):
 * 1. hash the file in the browser (SHA-256) and ask the API for a presigned PUT URL;
 * 2. PUT the file straight to object storage, reporting real progress;
 * 3. ask the API to verify the stored object. Only a verified asset is reported as uploaded.
 */

import { completeUpload, startUpload, type Asset } from "@/lib/admin/listening-api";

export const AUDIO_TYPES: Record<string, string> = {
  "audio/mpeg": "MP3",
  "audio/wav": "WAV",
  "audio/x-wav": "WAV",
  "audio/wave": "WAV",
  "audio/mp4": "M4A",
  "audio/x-m4a": "M4A",
};
export const IMAGE_TYPES: Record<string, string> = {
  "image/png": "PNG",
  "image/jpeg": "JPEG",
  "image/webp": "WebP",
};

export type UploadPhase = "hashing" | "uploading" | "verifying";

export class UploadError extends Error {}

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function put(
  url: string,
  file: Blob,
  headers: Record<string, string>,
  onProgress: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new UploadError(`Storage rejected the upload (HTTP ${xhr.status}).`));
    xhr.onerror = () => reject(new UploadError("The upload could not reach media storage."));
    xhr.onabort = () => reject(new UploadError("The upload was cancelled."));
    xhr.send(file);
  });
}

export async function uploadMedia(
  file: File,
  {
    testId,
    kind,
    onPhase,
    onProgress,
  }: {
    testId: string;
    kind: "audio" | "image";
    onPhase: (phase: UploadPhase) => void;
    onProgress: (fraction: number) => void;
  },
): Promise<Asset> {
  const allowed = kind === "audio" ? AUDIO_TYPES : IMAGE_TYPES;
  if (!(file.type in allowed)) {
    throw new UploadError(
      `Unsupported file type. Use ${[...new Set(Object.values(allowed))].join(", ")}.`,
    );
  }
  onPhase("hashing");
  const sha256 = await sha256Hex(file);
  const ticket = await startUpload({
    test_id: testId,
    kind,
    filename: file.name,
    mime_type: file.type,
    size_bytes: file.size,
    sha256,
  });
  onPhase("uploading");
  await put(ticket.upload_url, file, ticket.headers, onProgress);
  onPhase("verifying");
  return completeUpload(ticket.asset.id);
}
