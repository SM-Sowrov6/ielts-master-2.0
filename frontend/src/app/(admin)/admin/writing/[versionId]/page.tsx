import type { Metadata } from "next";

import { ProductiveEditor } from "@/components/admin/productive/productive-editor";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Edit Writing test" };

export default async function WritingEditorPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  const path = `/admin/writing/${encodeURIComponent(versionId)}`;
  const user = await requireStaff(path);
  return (
    <StaffOnly path={path}>
      {user && (
        <AdminModuleProvider module="writing">
          <ProductiveEditor versionId={versionId} user={user} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
