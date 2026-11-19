import type { Metadata } from "next";

import { adminNav, navItem } from "@/components/layout/nav-config";
import { StaffOnly } from "@/components/auth/gates";
import { ComingSoon } from "@/components/patterns/coming-soon";

const item = navItem(adminNav, "/admin/settings");

export const metadata: Metadata = { title: item.label };

export default function Page() {
  return (
    <StaffOnly path="/admin/settings">
      <ComingSoon item={item} />
    </StaffOnly>
  );
}
