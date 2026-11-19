import hashlib
from pathlib import Path

import pytest

from ielts_ai.prompts import PromptRegistry, PromptRegistryError


def _write(root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_discovers_versions_and_selects_latest_semver(tmp_path: Path) -> None:
    _write(tmp_path, "writing/criterion_lr@1.2.0.md", "v1.2")
    _write(tmp_path, "writing/criterion_lr@1.10.0.md", "v1.10")  # semver, not lexical
    _write(tmp_path, "writing/README.md", "ignored")
    registry = PromptRegistry.from_directory(tmp_path)

    assert registry.keys() == ["writing.criterion_lr"]
    latest = registry.get("writing.criterion_lr")
    assert latest.version == "1.10.0"
    assert latest.content_hash == hashlib.sha256(b"v1.10").hexdigest()
    assert registry.get("writing.criterion_lr", "1.2.0").body == "v1.2"


def test_invalid_versioned_filename_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "writing/criterion_lr@1.0.md", "missing patch")
    with pytest.raises(PromptRegistryError, match="Invalid prompt filename"):
        PromptRegistry.from_directory(tmp_path)


def test_unknown_key_and_version_raise(tmp_path: Path) -> None:
    _write(tmp_path, "coach/system@1.0.0.md", "x")
    registry = PromptRegistry.from_directory(tmp_path)
    with pytest.raises(PromptRegistryError):
        registry.get("coach.missing")
    with pytest.raises(PromptRegistryError):
        registry.get("coach.system", "9.9.9")


def test_shipped_prompt_directory_loads() -> None:
    import ielts_ai.prompts as prompts_pkg

    root = Path(prompts_pkg.__file__).parent
    assert PromptRegistry.from_directory(root).keys() == ["speaking.evaluate", "writing.evaluate"]
