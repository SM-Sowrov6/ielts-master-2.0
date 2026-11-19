import type { Metadata } from "next";

import { ListeningDashboard } from "@/components/admin/listening/listening-dashboard";
import { StaffOnly } from "@/components/auth/gates";
import { AdminModuleProvider } from "@/lib/admin/module";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Speaking Management" };

export default async function SpeakingManagementPage() {
  const user = await requireStaff("/admin/speaking");
  return (
    <StaffOnly path="/admin/speaking">
      {user && (
        <AdminModuleProvider module="speaking">
          <ListeningDashboard permissions={user.permissions} />
        </AdminModuleProvider>
      )}
    </StaffOnly>
  );
}
