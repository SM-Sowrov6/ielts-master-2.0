import type { Metadata } from "next";

import { ProductiveEditor } from "@/components/admin/productive/productive-editor";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Edit Speaking test" };

export default async function SpeakingEditorPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  const path = `/admin/speaking/${encodeURIComponent(versionId)}`;
  const user = await requireStaff(path);
  return (
    <StaffOnly path={path}>
      {user && (
        <AdminModuleProvider module="speaking">
          <ProductiveEditor versionId={versionId} user={user} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
