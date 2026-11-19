import type { Metadata } from "next";

import { ProductivePreview } from "@/components/admin/productive/productive-preview";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";

export const metadata: Metadata = { title: "Preview Speaking test" };

export default async function SpeakingPreviewPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  return (
    <StaffOnly path={`/admin/speaking/${encodeURIComponent(versionId)}/preview`}>
      <AdminModuleProvider module="speaking">
        <ProductivePreview versionId={versionId} />
      </AdminModuleProvider>
    </StaffOnly>
  );
}
