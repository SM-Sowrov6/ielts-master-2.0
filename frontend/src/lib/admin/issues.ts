/**
 * Maps validator issue locations (e.g. "listening/common > section 2 > group 1 (mcq_single) > Q11")
 * onto the editor's structure, so each problem is shown next to the field it concerns.
 */

import type { Issue } from "@/lib/admin/listening-api";

export type IssueTarget = { section?: number; group?: number; question?: number };

export function issueTarget(location: string): IssueTarget {
  const section = /section (\d+)/.exec(location);
  const group = /group (\d+)/.exec(location);
  const question = /> Q(\d+)/.exec(location);
  return {
    section: section ? Number(section[1]) : undefined,
    group: group ? Number(group[1]) - 1 : undefined, // 0-based index in the section
    question: question ? Number(question[1]) : undefined,
  };
}

export function issuesFor(issues: readonly Issue[], where: IssueTarget): Issue[] {
  return issues.filter((issue) => {
    const t = issueTarget(issue.location);
    if (where.section !== undefined && t.section !== where.section) return false;
    if (where.group !== undefined && t.group !== where.group) return false;
    if (where.question !== undefined && t.question !== where.question) return false;
    // Exact level: a section-level filter does not repeat group/question issues.
    if (where.group === undefined && t.group !== undefined) return false;
    if (where.question === undefined && t.question !== undefined) return false;
    return true;
  });
}

export function countErrors(issues: readonly Issue[]): number {
  return issues.filter((i) => i.severity === "error").length;
}

type RequestError = { loc: (string | number)[]; msg: string; code: string };
type SectionShape = {
  section_no: number;
  groups?: { question_type: string; questions: { number_from: number }[] }[] | null;
};

const FRIENDLY: Record<string, string> = {
  answers: "Add the correct answer.",
  value: "The answer cannot be empty.",
  text: "Every option needs text.",
  label: "Every option needs a letter or label.",
  questions: "A question group needs at least one question.",
  number_from: "Question numbers must be between 1 and 40.",
  number_to: "Question numbers must be between 1 and 40.",
  title: "Enter a title (at most 300 characters).",
  body: "The explanation cannot be empty.",
};

/**
 * FastAPI request-schema errors (422 `validation_error`, e.g. a question without an answer yet)
 * placed on the same section/group/question as content-validator issues, in plain language.
 */
export function requestErrorsToIssues(
  errors: readonly RequestError[],
  sections: readonly SectionShape[],
): Issue[] {
  return errors.map((e) => {
    const at = (key: string) => {
      const i = e.loc.indexOf(key);
      const next = i >= 0 ? e.loc[i + 1] : undefined;
      return typeof next === "number" ? next : undefined;
    };
    const si = at("sections");
    const gi = at("groups");
    const qi = at("questions");
    let location = "test";
    if (si !== undefined) {
      const section = sections[si];
      location = `listening/common > section ${section?.section_no ?? si + 1}`;
      if (gi !== undefined) {
        const group = section?.groups?.[gi];
        location += ` > group ${gi + 1} (${group?.question_type ?? "group"})`;
        if (qi !== undefined) location += ` > Q${group?.questions[qi]?.number_from ?? qi + 1}`;
      }
    }
    const field = [...e.loc].reverse().find((p): p is string => typeof p === "string") ?? "";
    return {
      severity: "error" as const,
      code: e.code,
      location,
      message: FRIENDLY[field] ?? `${field.replaceAll("_", " ")}: ${e.msg}`,
    };
  });
}
