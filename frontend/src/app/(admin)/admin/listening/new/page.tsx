import type { Metadata } from "next";

import { CreateTestForm } from "@/components/admin/listening/create-test-form";
import { StaffOnly } from "@/components/auth/gates";
import { PageHeader } from "@/components/patterns/page-header";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "New Listening test" };

export default async function NewListeningTestPage() {
  const user = await requireStaff("/admin/listening/new");
  return (
    <StaffOnly path="/admin/listening/new">
      <PageHeader
        title="New Listening test"
        description="Start with the basic information. Sections, audio and questions are added in the editor next."
      />
      {user && <CreateTestForm permissions={user.permissions} />}
    </StaffOnly>
  );
}
