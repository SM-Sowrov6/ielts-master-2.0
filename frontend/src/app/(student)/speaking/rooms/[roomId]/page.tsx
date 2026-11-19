import type { Metadata } from "next";

import { SignedIn } from "@/components/auth/gates";
import { SpeakingRoom } from "@/components/speaking-room/room";

export const metadata: Metadata = { title: "Speaking Room", robots: { index: false } };

export default async function SpeakingRoomPage({
  params,
}: {
  params: Promise<{ roomId: string }>;
}) {
  const { roomId } = await params;
  return (
    <SignedIn path={`/speaking/rooms/${encodeURIComponent(roomId)}`}>
      <SpeakingRoom roomId={roomId} />
    </SignedIn>
  );
}
