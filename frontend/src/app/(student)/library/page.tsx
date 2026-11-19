import type { Metadata } from "next";

import { studentNav, navItem } from "@/components/layout/nav-config";
import { ComingSoon } from "@/components/patterns/coming-soon";

const item = navItem(studentNav, "/library");

export const metadata: Metadata = { title: item.label };

export default function Page() {
  return <ComingSoon item={item} />;
}
