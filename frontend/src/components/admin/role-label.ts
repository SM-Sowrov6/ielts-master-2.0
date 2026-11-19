/** Display names for the seeded roles (migration 0006). Unknown codes are shown as-is. */
const ROLE_LABELS: Record<string, string> = {
  super_admin: "Super admin",
  admin: "Admin",
  content_manager: "Content manager",
  reviewer: "Reviewer",
  student: "Student",
};

export function roleLabel(code: string): string {
  return ROLE_LABELS[code] ?? code;
}

const RANK = ["super_admin", "admin", "content_manager", "reviewer", "student"];

/** The most privileged role first. */
export function sortRoles(roles: readonly string[]): string[] {
  const rank = (code: string) => {
    const index = RANK.indexOf(code);
    return index === -1 ? RANK.length : index;
  };
  return [...roles].sort((a, b) => rank(a) - rank(b));
}
