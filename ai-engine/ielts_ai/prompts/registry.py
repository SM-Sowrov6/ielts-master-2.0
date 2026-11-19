"""File-based prompt registry.

Layout: `<root>/<feature>/<name>@<major>.<minor>.<patch>.md` → key `<feature>.<name>`.
Each template's SHA-256 is recorded so every evaluation can cite the exact prompt used
(registered in `prompt_versions` by the backend at deploy time).
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_FILENAME = re.compile(r"^(?P<name>[a-z][a-z0-9_]*)@(?P<version>\d+\.\d+\.\d+)\.md$")


class PromptRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    key: str
    version: str
    body: str
    content_hash: str

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        major, minor, patch = (int(p) for p in self.version.split("."))
        return major, minor, patch


class PromptRegistry:
    def __init__(self, templates: dict[str, dict[str, PromptTemplate]]) -> None:
        self._templates = templates

    @classmethod
    def from_directory(cls, root: Path) -> PromptRegistry:
        templates: dict[str, dict[str, PromptTemplate]] = {}
        for path in sorted(root.glob("*/*.md")):
            match = _FILENAME.fullmatch(path.name)
            if match is None:
                if "@" in path.name:
                    raise PromptRegistryError(f"Invalid prompt filename: {path.name}")
                continue  # e.g. README.md
            key = f"{path.parent.name}.{match['name']}"
            body = path.read_text(encoding="utf-8")
            template = PromptTemplate(
                key=key,
                version=match["version"],
                body=body,
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
            )
            templates.setdefault(key, {})[template.version] = template
        return cls(templates)

    def keys(self) -> list[str]:
        return sorted(self._templates)

    def get(self, key: str, version: str | None = None) -> PromptTemplate:
        versions = self._templates.get(key)
        if not versions:
            raise PromptRegistryError(f"Unknown prompt key: {key}")
        if version is None:
            return max(versions.values(), key=lambda t: t.version_tuple)
        try:
            return versions[version]
        except KeyError:
            raise PromptRegistryError(f"Unknown version {version} for prompt {key}") from None
