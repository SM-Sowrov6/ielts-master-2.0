import type { Metadata } from "next";

import { ListeningDashboard } from "@/components/admin/listening/listening-dashboard";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Reading Management" };

export default async function ReadingManagementPage() {
  const user = await requireStaff("/admin/reading");
  return (
    <StaffOnly path="/admin/reading">
      {user && (
        <AdminModuleProvider module="reading">
          <ListeningDashboard permissions={user.permissions} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
