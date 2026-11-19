import type { Metadata } from "next";

import { ListeningEditor } from "@/components/admin/listening/editor/listening-editor";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Edit Reading test" };

export default async function ReadingEditorPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  const path = `/admin/reading/${encodeURIComponent(versionId)}`;
  const user = await requireStaff(path);
  return (
    <StaffOnly path={path}>
      {user && (
        <AdminModuleProvider module="reading">
          <ListeningEditor versionId={versionId} user={user} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
