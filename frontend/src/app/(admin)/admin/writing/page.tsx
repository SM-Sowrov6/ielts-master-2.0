import type { Metadata } from "next";

import { ListeningDashboard } from "@/components/admin/listening/listening-dashboard";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Writing Management" };

export default async function WritingManagementPage() {
  const user = await requireStaff("/admin/writing");
  return (
    <StaffOnly path="/admin/writing">
      {user && (
        <AdminModuleProvider module="writing">
          <ListeningDashboard permissions={user.permissions} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
