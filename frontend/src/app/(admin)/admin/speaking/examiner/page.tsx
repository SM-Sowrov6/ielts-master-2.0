import type { Metadata } from "next";

import { ExaminerOverview } from "@/components/admin/examiner/examiner-admin";
import { StaffOnly } from "@/components/auth/gates";
import { PageHeader } from "@/components/patterns/page-header";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "AI Examiner Configuration" };

export default async function ExaminerPage() {
  const user = await requireStaff("/admin/speaking/examiner");
  return (
    <StaffOnly path="/admin/speaking/examiner">
      <PageHeader
        title="AI Examiner Configuration"
        description="How the AI examiner conducts each published Speaking test: question order, timing, follow-ups, instructions and criteria, plus the examiner personas candidates choose from."
      />
      {user && <ExaminerOverview user={user} />}
    </StaffOnly>
  );
}
