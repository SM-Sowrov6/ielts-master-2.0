import type { Metadata } from "next";

import { CreateTestForm } from "@/components/admin/listening/create-test-form";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { PageHeader } from "@/components/patterns/page-header";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "New Speaking test" };

export default async function NewSpeakingTestPage() {
  const user = await requireStaff("/admin/speaking/new");
  return (
    <StaffOnly path="/admin/speaking/new">
      <PageHeader
        title="New Speaking test"
        description="Start with the basic information. Tasks, parts and model answers are added in the editor next."
      />
      {user && (
        <AdminModuleProvider module="speaking">
          <CreateTestForm permissions={user.permissions} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
