import type { Metadata } from "next";

import { CreateTestForm } from "@/components/admin/listening/create-test-form";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { PageHeader } from "@/components/patterns/page-header";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "New Reading test" };

export default async function NewReadingTestPage() {
  const user = await requireStaff("/admin/reading/new");
  return (
    <StaffOnly path="/admin/reading/new">
      <PageHeader
        title="New Reading test"
        description="Start with the basic information. Passages and questions are added in the editor next."
      />
      {user && (
        <AdminModuleProvider module="reading">
          <CreateTestForm permissions={user.permissions} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
