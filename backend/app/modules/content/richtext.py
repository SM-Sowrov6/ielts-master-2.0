"""Allow-list validation for rich text stored as ProseMirror JSON (docs/SECURITY_GUIDELINES.md §5).

Content is never stored or rendered as raw HTML. Any node, mark or attribute outside this list is
an authoring error. `blank` nodes (numbered gaps in completion templates) are only allowed where
the caller says so.
"""

from typing import Any

_NODE_ATTRS: dict[str, set[str]] = {
    "doc": set(),
    "paragraph": set(),
    "text": set(),
    "heading": {"level"},
    "bulletList": set(),
    "orderedList": {"start"},
    "listItem": set(),
    "hardBreak": set(),
    "table": set(),
    "tableRow": set(),
    "tableCell": {"colspan", "rowspan"},
    "tableHeader": {"colspan", "rowspan"},
}
_MARKS = {"bold", "italic", "underline"}
_MAX_DEPTH = 20


def validate_doc(doc: Any, *, allow_blanks: bool = False) -> tuple[list[str], set[int]]:
    """Return (errors, blank question numbers found)."""
    errors: list[str] = []
    blanks: set[int] = set()

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > _MAX_DEPTH:
            errors.append(f"{path}: nesting deeper than {_MAX_DEPTH}")
            return
        if not isinstance(node, dict):
            errors.append(f"{path}: node must be an object")
            return
        node_type = node.get("type")
        allowed_attrs = _NODE_ATTRS.get(str(node_type))
        if node_type == "blank" and allow_blanks:
            allowed_attrs = {"number"}
            number = (node.get("attrs") or {}).get("number")
            if not isinstance(number, int) or number < 1:
                errors.append(f"{path}: blank needs a positive integer 'number'")
            elif number in blanks:
                errors.append(f"{path}: blank {number} appears more than once")
            else:
                blanks.add(number)
        if allowed_attrs is None:
            errors.append(f"{path}: node type {node_type!r} is not allowed")
            return
        unknown_keys = set(node) - {"type", "attrs", "content", "text", "marks"}
        if unknown_keys:
            errors.append(f"{path}: unexpected keys {sorted(unknown_keys)}")
        attrs = node.get("attrs") or {}
        if not isinstance(attrs, dict) or set(attrs) - allowed_attrs:
            errors.append(f"{path}: attributes not allowed on {node_type!r}")
        if node_type == "text":
            if not isinstance(node.get("text"), str) or not node["text"]:
                errors.append(f"{path}: text node needs non-empty 'text'")
            for mark in node.get("marks") or []:
                if (
                    not isinstance(mark, dict)
                    or mark.get("type") not in _MARKS
                    or set(mark) - {"type"}
                ):
                    errors.append(f"{path}: mark {mark!r} is not allowed")
        elif "text" in node or "marks" in node:
            errors.append(f"{path}: only text nodes may carry text or marks")
        children = node.get("content") or []
        if not isinstance(children, list):
            errors.append(f"{path}: 'content' must be a list")
            return
        for index, child in enumerate(children):
            walk(child, f"{path}.content[{index}]", depth + 1)

    if not isinstance(doc, dict) or doc.get("type") != "doc":
        return (["root must be a {'type': 'doc'} node"], blanks)
    walk(doc, "doc", 0)
    return errors, blanks


def plain_doc(text: str) -> dict[str, Any]:
    """Convenience: wrap plain text paragraphs into a minimal valid document."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": p.strip()}]}
            for p in paragraphs
        ],
    }
