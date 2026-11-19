import { redirect } from "next/navigation";

import type { Me } from "@/lib/auth/api";
import { destinationAfterSignIn } from "@/lib/auth/redirect";
import { getServerUser } from "@/lib/auth/server";

/**
 * Signed-in visitors skip sign-in/registration (staff go to the admin console, students to their
 * dashboard). If the API is unreachable, show the form.
 */
export async function redirectIfSignedIn(next?: string): Promise<void> {
  let user: Me | null = null;
  try {
    user = await getServerUser();
  } catch {
    user = null;
  }
  if (user) redirect(destinationAfterSignIn(user, next));
}
