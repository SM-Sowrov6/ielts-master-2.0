import type { Metadata } from "next";

import { ListeningHome } from "@/components/listening/listening-home";
import { SignedIn } from "@/components/auth/gates";

export const metadata: Metadata = { title: "Listening" };

export default function ListeningPage() {
  return (
    <SignedIn path="/listening">
      <ListeningHome />
    </SignedIn>
  );
}
