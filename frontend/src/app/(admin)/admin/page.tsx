import type { Metadata } from "next";

import {
  ContentOverviewWidget,
  ContentQuickAccess,
  RecentActivityWidget,
  SystemOverviewWidget,
  UsersOverviewWidget,
  WelcomePanel,
} from "@/components/admin/dashboard/widgets";
import { StaffOnly } from "@/components/auth/gates";
import {
  fetchContentOverview,
  fetchRecentActivity,
  fetchSystemStatus,
  fetchUsersOverview,
} from "@/lib/admin/server";
import { requireStaff } from "@/lib/auth/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Admin dashboard" };

/**
 * Super Admin dashboard. Every number comes from a backend read that is authorised per widget
 * (users.read, content.* , audit.read); widgets without permission or data say so.
 */
export default async function AdminDashboardPage() {
  return (
    <StaffOnly path="/admin">
      <Dashboard />
    </StaffOnly>
  );
}

async function Dashboard() {
  const user = await requireStaff("/admin");
  if (!user) return null; // <StaffOnly> already rendered the denial
  const [content, users, activity, system] = await Promise.all([
    fetchContentOverview(),
    fetchUsersOverview(),
    fetchRecentActivity(),
    fetchSystemStatus(),
  ]);
  return (
    <div className="space-y-6">
      <WelcomePanel user={user} />
      <ContentQuickAccess />
      <div className="grid gap-6 xl:grid-cols-2">
        <ContentOverviewWidget read={content} />
        <UsersOverviewWidget read={users} />
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <RecentActivityWidget read={activity} />
        <SystemOverviewWidget system={system} />
      </div>
    </div>
  );
}
