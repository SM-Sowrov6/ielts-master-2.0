import Link from "next/link";
import type { ReactNode } from "react";

import { safeInternalHref } from "@/lib/assistant/routes";

/**
 * Minimal, safe Markdown for assistant replies: paragraphs, bullet/numbered lists, **bold**,
 * `code` and links. Built as React elements (no HTML injection); only same-site paths become
 * links, so the model cannot send users to external sites.
 */

const INLINE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^)\s]+\))/g;

function inline(text: string, onNavigate?: () => void): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      // Bold may wrap a link or code (e.g. **[Reading](/reading)**): parse its inside too.
      return <strong key={i}>{inline(part.slice(2, -2), onNavigate)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      const href = safeInternalHref(link[2] ?? "");
      if (!href) return <span key={i}>{link[1]}</span>;
      return (
        <Link
          key={i}
          href={href}
          onClick={onNavigate}
          className="font-medium text-primary underline underline-offset-2 hover:no-underline"
        >
          {link[1]}
        </Link>
      );
    }
    return part;
  });
}

type Block = { kind: "p"; lines: string[] } | { kind: "ul" | "ol"; items: string[] };

function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    const last = out.at(-1);
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? numbered)![1] ?? "";
      if (last && last.kind === kind) last.items.push(item);
      else out.push({ kind, items: [item] });
    } else if (line.trim() === "") {
      out.push({ kind: "p", lines: [] });
    } else {
      // Headings are shown as bold lines (no heading levels inside a chat bubble).
      const heading = /^#{1,6}\s+/.exec(line);
      const text = heading ? `**${line.slice(heading[0].length).replace(/\*\*/g, "")}**` : line;
      if (last && last.kind === "p" && last.lines.length > 0) last.lines.push(text);
      else out.push({ kind: "p", lines: [text] });
    }
  }
  return out.filter((b) => (b.kind === "p" ? b.lines.length > 0 : b.items.length > 0));
}

export function AssistantMarkdown({ text, onNavigate }: { text: string; onNavigate?: () => void }) {
  return (
    <div className="space-y-2 break-words">
      {blocks(text).map((block, i) => {
        if (block.kind === "p") {
          return (
            <p key={i}>
              {block.lines.map((line, j) => (
                <span key={j}>
                  {j > 0 && <br />}
                  {inline(line, onNavigate)}
                </span>
              ))}
            </p>
          );
        }
        const List = block.kind;
        return (
          <List
            key={i}
            className={List === "ul" ? "list-disc space-y-1 pl-5" : "list-decimal space-y-1 pl-5"}
          >
            {block.items.map((item, j) => (
              <li key={j}>{inline(item, onNavigate)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
