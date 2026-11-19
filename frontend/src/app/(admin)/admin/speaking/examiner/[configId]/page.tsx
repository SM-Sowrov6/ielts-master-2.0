import type { Metadata } from "next";

import { ExaminerConfigEditor } from "@/components/admin/examiner/examiner-admin";
import { StaffOnly } from "@/components/auth/gates";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Edit examiner configuration" };

export default async function ExaminerConfigPage({
  params,
}: {
  params: Promise<{ configId: string }>;
}) {
  const { configId } = await params;
  const path = `/admin/speaking/examiner/${encodeURIComponent(configId)}`;
  const user = await requireStaff(path);
  return (
    <StaffOnly path={path}>
      {user && <ExaminerConfigEditor configId={configId} user={user} />}
    </StaffOnly>
  );
}
