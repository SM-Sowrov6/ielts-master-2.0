import type { Metadata } from "next";

import { ListeningPreview } from "@/components/admin/listening/listening-preview";
import { StaffOnly } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Preview Listening test" };

export default async function ListeningPreviewPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  return (
    <StaffOnly path={`/admin/listening/${encodeURIComponent(versionId)}/preview`}>
      <ListeningPreview versionId={versionId} />
    </StaffOnly>
  );
}
