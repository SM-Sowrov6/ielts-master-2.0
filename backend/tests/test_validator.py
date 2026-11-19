"""Version validator on in-memory trees built from the synthetic import payload (no database)."""

import uuid
from datetime import date, timedelta
from typing import Any

from content_fixtures import doc, synthetic_payload

from app.modules.content.enums import AssetStatus
from app.modules.content.importer import TestVersionImport, build_version_tree
from app.modules.content.models import ContentLicence, MediaAsset
from app.modules.content.question_types.base import ValidationIssue
from app.modules.content.validator import Stage, ValidationContext, has_errors, validate_version

TODAY = date(2026, 11, 18)


def _licence(valid_until: date | None = None) -> ContentLicence:
    return ContentLicence(
        id=uuid.uuid4(), source_type="original", licensor="Synthetic", valid_until=valid_until
    )


def _validate(
    payload: dict[str, Any], stage: Stage = "import", **ctx: Any
) -> list[ValidationIssue]:
    version, issues = build_version_tree(TestVersionImport.model_validate(payload))
    context = ValidationContext(
        today=TODAY,
        stage=stage,
        licence=ctx.get("licence", _licence()),
        assets=ctx.get("assets", {}),
    )
    return issues + validate_version(version, context)


def _codes(issues: list[ValidationIssue], *, errors: bool) -> set[str]:
    return {i.code for i in issues if i.is_error == errors}


def test_synthetic_test_is_importable_with_completeness_warnings() -> None:
    issues = _validate(synthetic_payload())
    assert not has_errors(issues), [i for i in issues if i.is_error]
    assert {"listening_audio_missing", "band_table_missing"} <= _codes(issues, errors=False)


def test_publish_stage_turns_completeness_into_errors() -> None:
    issues = _validate(synthetic_payload(), stage="publish")
    assert "listening_audio_missing" in _codes(issues, errors=True)
    assert "band_table_missing" in _codes(
        issues, errors=False
    )  # stays a warning (no band data yet)


def test_publish_passes_with_ready_audio_and_flags_unready_assets() -> None:
    ids = [uuid.uuid4() for _ in range(4)]
    assets = {i: MediaAsset(id=i, kind="audio", status=AssetStatus.READY.value) for i in ids}
    issues = _validate(
        synthetic_payload(audio_asset_ids=[str(i) for i in ids]), stage="publish", assets=assets
    )
    assert not has_errors(issues), [i for i in issues if i.is_error]
    assets[ids[0]].status = AssetStatus.PROCESSING.value
    unready = _validate(
        synthetic_payload(audio_asset_ids=[str(i) for i in ids]), stage="publish", assets=assets
    )
    assert "asset_not_ready" in _codes(unready, errors=True)
    missing = _validate(
        synthetic_payload(audio_asset_ids=[str(i) for i in ids]), stage="publish", assets={}
    )
    assert "asset_not_found" in _codes(missing, errors=True)


def test_expired_or_missing_licence_blocks_even_import() -> None:
    expired = _validate(
        synthetic_payload(), licence=_licence(valid_until=TODAY - timedelta(days=1))
    )
    assert "licence_invalid" in _codes(expired, errors=True)
    none = _validate(synthetic_payload(), licence=None)
    assert "licence_missing" in _codes(none, errors=True)


def test_numbering_rules() -> None:
    payload = synthetic_payload()
    reading = payload["modules"][1]
    reading["sections"][0]["groups"][0]["questions"][1]["number_from"] = 1  # duplicate Q1
    issues = _validate(payload)
    assert "question_numbers_duplicate" in _codes(issues, errors=True)

    payload = synthetic_payload()
    payload["modules"][1]["sections"][2]["groups"][2]["questions"].pop()  # 39 questions
    gap = _validate(payload)
    assert "question_count" in _codes(gap, errors=False)
    assert "question_count" in _codes(_validate(payload, stage="publish"), errors=True)


def test_type_must_belong_to_module_and_variants_are_checked() -> None:
    payload = synthetic_payload()
    payload["modules"][0]["sections"][0]["groups"][0]["question_type"] = "tfng"  # reading-only type
    assert "question_type_not_in_module" in _codes(_validate(payload), errors=True)
    payload = synthetic_payload()
    payload["modules"][0]["variant"] = "academic"  # listening is always common
    assert "module_variant_invalid" in _codes(_validate(payload), errors=True)


def test_writing_task_kind_must_match_variant() -> None:
    payload = synthetic_payload()
    payload["modules"][2]["writing_tasks"][0]["task_kind"] = "gt_letter"
    assert "writing_task_kind" in _codes(_validate(payload), errors=True)


def test_rich_text_allow_list_and_key_notation_errors() -> None:
    payload = synthetic_payload()
    payload["modules"][1]["sections"][0]["passages"][0]["body"] = {
        "type": "doc",
        "content": [{"type": "html", "text": "<script>alert(1)</script>"}],
    }
    payload["modules"][0]["sections"][0]["groups"][0]["questions"][0]["answers"][0]["value"] = (
        "(the library"
    )
    issues = _validate(payload)
    assert {"rich_text_invalid", "key_notation_invalid"} <= _codes(issues, errors=True)


def test_unknown_evidence_paragraph_is_reported() -> None:
    payload = synthetic_payload()
    payload["modules"][1]["sections"][0]["groups"][0]["questions"][0]["explanation"] = {
        "body": doc("x"),
        "evidence_paragraph_label": "Z",
    }
    assert "evidence_paragraph_unknown" in _codes(_validate(payload), errors=True)


def test_speaking_part_two_needs_a_cue_card() -> None:
    payload = synthetic_payload()
    del payload["modules"][3]["speaking_parts"][1]["cue_card"]
    assert "cue_card_missing" in _codes(_validate(payload), errors=True)
