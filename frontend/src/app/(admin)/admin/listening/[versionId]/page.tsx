import type { Metadata } from "next";

import { ListeningEditor } from "@/components/admin/listening/editor/listening-editor";
import { StaffOnly } from "@/components/auth/gates";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Edit Listening test" };

export default async function ListeningEditorPage({
  params,
}: {
  params: Promise<{ versionId: string }>;
}) {
  const { versionId } = await params;
  const path = `/admin/listening/${encodeURIComponent(versionId)}`;
  const user = await requireStaff(path);
  return (
    <StaffOnly path={path}>
      {user && <ListeningEditor versionId={versionId} user={user} />}
    </StaffOnly>
  );
}
