import type { Metadata } from "next";

import { ListeningPreview } from "@/components/admin/listening/listening-preview";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";

export const metadata: Metadata = { title: "Preview Reading test" };

export default async function ReadingPreviewPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  return (
    <StaffOnly path={`/admin/reading/${encodeURIComponent(versionId)}/preview`}>
      <AdminModuleProvider module="reading">
        <ListeningPreview versionId={versionId} />
      </AdminModuleProvider>
    </StaffOnly>
  );
}
