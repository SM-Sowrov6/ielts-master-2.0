import type { Metadata } from "next";

import { ListeningDashboard } from "@/components/admin/listening/listening-dashboard";
import { StaffOnly } from "@/components/auth/gates";
import { requireStaff } from "@/lib/auth/server";

export const metadata: Metadata = { title: "Listening Management" };

export default async function ListeningManagementPage() {
  const user = await requireStaff("/admin/listening");
  return (
    <StaffOnly path="/admin/listening">
      {user && <ListeningDashboard permissions={user.permissions} />}
    </StaffOnly>
  );
}
