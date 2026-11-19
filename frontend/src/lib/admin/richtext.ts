/**
 * Plain text <-> the allow-listed ProseMirror JSON the content domain stores
 * (backend app/modules/content/richtext.py). Each line becomes a paragraph; no HTML is ever
 * produced or parsed. Richer formatting (tables, templates with blanks) can be added later with
 * a proper editor without changing the stored format.
 */

type Node = { type: string; text?: string; content?: Node[]; attrs?: Record<string, unknown> };
export type RichDoc = { [key: string]: unknown };

export function textToDoc(text: string): RichDoc | null {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  if (lines.every((line) => line.trim() === "")) return null;
  return {
    type: "doc",
    content: lines.map((line) =>
      line.trim() === ""
        ? { type: "paragraph" }
        : { type: "paragraph", content: [{ type: "text", text: line }] },
    ),
  };
}

function collect(node: Node, out: string[]): void {
  if (node.type === "text" && typeof node.text === "string") out.push(node.text);
  if (node.type === "blank") out.push(`[${String(node.attrs?.number ?? "")}]`);
  if (node.type === "hardBreak") out.push("\n");
  for (const child of node.content ?? []) collect(child, out);
}

export function docToText(doc: unknown): string {
  if (!doc || typeof doc !== "object") return "";
  const root = doc as Node;
  const blocks = root.type === "doc" ? (root.content ?? []) : [root];
  return blocks
    .map((block) => {
      const parts: string[] = [];
      collect(block, parts);
      return parts.join("");
    })
    .join("\n");
}
