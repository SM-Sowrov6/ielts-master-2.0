import type { Metadata } from "next";

import { ProductivePreview } from "@/components/admin/productive/productive-preview";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";

export const metadata: Metadata = { title: "Preview Writing test" };

export default async function WritingPreviewPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  return (
    <StaffOnly path={`/admin/writing/${encodeURIComponent(versionId)}/preview`}>
      <AdminModuleProvider module="writing">
        <ProductivePreview versionId={versionId} />
      </AdminModuleProvider>
    </StaffOnly>
  );
}
