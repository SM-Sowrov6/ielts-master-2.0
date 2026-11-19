"""Content domain against a real PostgreSQL (TEST_DATABASE_ADMIN_URL): migrations 0002-0005,
import, workflow, database triggers, constraints, search, audit."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from content_fixtures import synthetic_payload
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import DatabaseSettings
from app.core.database import create_engine, create_session_factory
from app.modules.audit.models import AuditLog
from app.modules.content import api as content_api
from app.modules.content import importer, service
from app.modules.content.enums import ReviewDecision, VersionStatus
from app.modules.content.errors import (
    ContentNotFoundError,
    ContentValidationError,
    ImportJobStateError,
    OpenDraftExistsError,
    ReviewRequiredError,
    SelfReviewError,
)
from app.modules.content.models import (
    Book,
    ContentLicence,
    MediaAsset,
    Question,
    QuestionOption,
    QuestionType,
    Test,
    TestVersion,
)
from app.modules.content.question_types import REGISTRY

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
AUTHOR = uuid.uuid4()
REVIEWER = uuid.uuid4()
Sessions = async_sessionmaker[AsyncSession]


@pytest.fixture
def content_db(test_database_url: str) -> str:
    """Ensure the test database is at head (other suites may downgrade it)."""
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["database_url"] = test_database_url
    command.upgrade(cfg, "head")
    return test_database_url


@pytest.fixture
async def sessions(content_db: str) -> AsyncIterator[Sessions]:
    engine = create_engine(DatabaseSettings(database_url=content_db))
    yield create_session_factory(engine)
    await engine.dispose()


def _slug() -> str:
    return f"synthetic-{uuid.uuid4().hex[:10]}"


async def _licence(sessions: Sessions, *, valid_until: Any = None) -> uuid.UUID:
    async with sessions() as session, session.begin():
        licence = ContentLicence(
            source_type="original", licensor="Synthetic test licensor", valid_until=valid_until
        )
        session.add(licence)
    return licence.id


async def _ready_audio(sessions: Sessions, licence_id: uuid.UUID) -> list[str]:
    async with sessions() as session, session.begin():
        assets = [
            MediaAsset(
                kind="audio",
                storage_key=f"test/{uuid.uuid4()}.m4a",
                mime_type="audio/mp4",
                status="ready",
                license_id=licence_id,
            )
            for _ in range(4)
        ]
        session.add_all(assets)
    return [str(a.id) for a in assets]


async def _import_draft(
    sessions: Sessions, payload: dict[str, Any], licence_id: uuid.UUID
) -> TestVersion:
    async with sessions() as session, session.begin():
        result = await importer.dry_run(
            session,
            json.dumps(payload).encode(),
            file_name="synthetic.json",
            license_id=licence_id,
            actor_id=AUTHOR,
        )
        assert result.ok, [i for i in result.issues if i.is_error]
        job_id = result.job.id
    async with sessions() as session, session.begin():
        return await importer.commit(session, job_id, actor_id=AUTHOR)


async def _publish(sessions: Sessions, version_id: uuid.UUID) -> None:
    async with sessions() as session, session.begin():
        await service.submit_for_review(session, version_id, actor_id=AUTHOR)
    async with sessions() as session, session.begin():
        await service.review_version(
            session, version_id, reviewer_id=REVIEWER, decision=ReviewDecision.APPROVED
        )
    async with sessions() as session, session.begin():
        await service.publish_version(session, version_id, actor_id=REVIEWER)


async def _published_test(sessions: Sessions) -> tuple[uuid.UUID, TestVersion]:
    licence_id = await _licence(sessions)
    audio = await _ready_audio(sessions, licence_id)
    draft = await _import_draft(
        sessions, synthetic_payload(slug=_slug(), audio_asset_ids=audio), licence_id
    )
    await _publish(sessions, draft.id)
    return licence_id, draft


# ----------------------------------------------------------------------------------- reference data
async def test_question_types_table_matches_registry(sessions: Sessions) -> None:
    async with sessions() as session:
        rows = (await session.scalars(select(QuestionType))).all()
    assert {r.code for r in rows} == set(REGISTRY)
    assert all(r.is_active and r.handler_version == "1.0.0" for r in rows)


# ----------------------------------------------------------------------------------- import
async def test_dry_run_writes_no_content_rows_and_records_the_job(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    async with sessions() as session:
        before = await session.scalar(select(func.count()).select_from(TestVersion))
        books_before = await session.scalar(select(func.count()).select_from(Book))
    async with sessions() as session, session.begin():
        result = await importer.dry_run(
            session,
            json.dumps(synthetic_payload(slug=_slug())).encode(),
            file_name="s.json",
            license_id=licence_id,
            actor_id=AUTHOR,
        )
    assert result.ok
    assert result.job.status == "validated"
    assert "listening_audio_missing" in {
        i.code for i in result.issues
    }  # warning: audio comes in 5b
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(TestVersion)) == before
        assert await session.scalar(select(func.count()).select_from(Book)) == books_before


async def test_invalid_payload_fails_with_locations_and_cannot_be_committed(
    sessions: Sessions,
) -> None:
    licence_id = await _licence(sessions)
    payload = synthetic_payload(slug=_slug())
    payload["modules"][0]["sections"][0]["groups"][1]["questions"][0]["answers"][0]["value"] = "Z"
    async with sessions() as session, session.begin():
        result = await importer.dry_run(
            session,
            json.dumps(payload).encode(),
            file_name="bad.json",
            license_id=licence_id,
            actor_id=AUTHOR,
        )
    assert result.job.status == "failed"
    bad = [i for i in result.issues if i.code == "key_not_an_option"]
    assert bad
    assert "section 1 > group 2 (mcq_single) > Q6" in bad[0].location
    async with sessions() as session, session.begin():
        with pytest.raises(ImportJobStateError):
            await importer.commit(session, result.job.id, actor_id=AUTHOR)


async def test_commit_creates_a_draft_once(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    async with sessions() as session, session.begin():
        result = await importer.dry_run(
            session,
            json.dumps(synthetic_payload(slug=_slug())).encode(),
            file_name="s.json",
            license_id=licence_id,
            actor_id=AUTHOR,
        )
    async with sessions() as session, session.begin():
        version = await importer.commit(session, result.job.id, actor_id=AUTHOR)
    assert (version.status, version.version_no, version.created_by) == ("draft", 1, AUTHOR)
    async with sessions() as session:
        tree = await service.load_version_tree(session, version.id)
        questions = [
            q for m in tree.modules for s in m.sections for g in s.groups for q in g.questions
        ]
        assert sum(q.marks for q in questions) == 80  # 40 listening + 40 reading
    async with sessions() as session, session.begin():
        with pytest.raises(ImportJobStateError):
            await importer.commit(session, result.job.id, actor_id=AUTHOR)


async def test_expired_licence_blocks_import(sessions: Sessions) -> None:
    licence_id = await _licence(sessions, valid_until=datetime.now(UTC).date() - timedelta(days=1))
    async with sessions() as session, session.begin():
        result = await importer.dry_run(
            session,
            json.dumps(synthetic_payload(slug=_slug())).encode(),
            file_name="s.json",
            license_id=licence_id,
            actor_id=AUTHOR,
        )
    assert "licence_invalid" in {i.code for i in result.issues if i.is_error}


# ----------------------------------------------------------------------------------- workflow
async def test_review_rules_and_publish(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    audio = await _ready_audio(sessions, licence_id)
    draft = await _import_draft(
        sessions, synthetic_payload(slug=_slug(), audio_asset_ids=audio), licence_id
    )
    async with sessions() as session, session.begin():
        warnings = await service.submit_for_review(session, draft.id, actor_id=AUTHOR)
    # The synthetic Academic Task 1 has no visual: flagged, not blocking.
    assert {w.code for w in warnings} == {"band_table_missing", "writing_visual_missing"}
    async with sessions() as session, session.begin():
        with pytest.raises(ReviewRequiredError):
            await service.publish_version(session, draft.id, actor_id=REVIEWER)
    async with sessions() as session, session.begin():
        with pytest.raises(SelfReviewError):
            await service.review_version(
                session, draft.id, reviewer_id=AUTHOR, decision=ReviewDecision.APPROVED
            )
    async with sessions() as session, session.begin():
        await service.review_version(
            session, draft.id, reviewer_id=REVIEWER, decision=ReviewDecision.APPROVED
        )
    async with sessions() as session, session.begin():
        await service.publish_version(session, draft.id, actor_id=REVIEWER)
    async with sessions() as session:
        version = await session.get_one(TestVersion, draft.id)
        test = await session.get_one(Test, version.test_id)
        actions = set(
            (
                await session.scalars(select(AuditLog.action).where(AuditLog.entity_id == draft.id))
            ).all()
        )
    assert version.status == "published"
    assert version.published_by == REVIEWER
    assert test.current_published_version_id == draft.id
    assert {
        "content.test_version.submit",
        "content.test_version.review",
        "content.test_version.publish",
    } <= actions


async def test_submit_without_audio_fails_publish_validation(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    draft = await _import_draft(sessions, synthetic_payload(slug=_slug()), licence_id)
    async with sessions() as session, session.begin():
        with pytest.raises(ContentValidationError) as excinfo:
            await service.submit_for_review(session, draft.id, actor_id=AUTHOR)
    assert "listening_audio_missing" in {i.code for i in excinfo.value.issues if i.is_error}


async def test_new_draft_deep_copies_and_republish_archives_previous(sessions: Sessions) -> None:
    _, v1 = await _published_test(sessions)
    async with sessions() as session, session.begin():
        v2 = await service.create_next_draft(session, v1.test_id, actor_id=AUTHOR)
    async with sessions() as session:
        with pytest.raises(OpenDraftExistsError):  # only one open version per test
            async with session.begin():
                await service.create_next_draft(session, v1.test_id, actor_id=AUTHOR)
    async with sessions() as session:
        old = await service.load_version_tree(session, v1.id)
        new = await service.load_version_tree(session, v2.id)

    def questions(v: TestVersion) -> list[Question]:
        return [q for m in v.modules for s in m.sections for g in s.groups for q in g.questions]

    assert v2.version_no == 2
    assert {q.lineage_id for q in questions(old)} == {q.lineage_id for q in questions(new)}
    assert not {q.id for q in questions(old)} & {q.id for q in questions(new)}
    new_paragraphs = {
        p.id for m in new.modules for s in m.sections for ps in s.passages for p in ps.paragraphs
    }
    evidence = {
        q.explanation.evidence_paragraph_id
        for q in questions(new)
        if q.explanation and q.explanation.evidence_paragraph_id
    }
    assert evidence
    assert evidence <= new_paragraphs

    await _publish(sessions, v2.id)
    async with sessions() as session:
        statuses = dict(
            (
                await session.execute(
                    select(TestVersion.version_no, TestVersion.status).where(
                        TestVersion.test_id == v1.test_id
                    )
                )
            ).all()
        )
        test = await session.get_one(Test, v1.test_id)
    assert statuses == {1: "archived", 2: "published"}
    assert test.current_published_version_id == v2.id


# ----------------------------------------------------------------------------------- triggers
async def _expect_db_error(
    sessions: Sessions, sql: str, params: dict[str, Any], fragment: str
) -> None:
    async with sessions() as session:
        with pytest.raises(DBAPIError, match=fragment):
            async with session.begin():
                await session.execute(text(sql), params)


async def test_published_content_is_immutable_in_the_database(sessions: Sessions) -> None:
    _, version = await _published_test(sessions)
    async with sessions() as session:
        tree = await service.load_version_tree(session, version.id)
    group = tree.modules[0].sections[0].groups[0]
    question = group.questions[0]
    await _expect_db_error(
        sessions,
        "UPDATE questions SET stem = '{}'::jsonb WHERE id = :id",
        {"id": question.id},
        "content_version_immutable",
    )
    await _expect_db_error(
        sessions,
        "DELETE FROM answer_keys WHERE question_id = :id",
        {"id": question.id},
        "content_version_immutable",
    )
    await _expect_db_error(
        sessions,
        "INSERT INTO question_options (id, group_id, label, text) "
        "VALUES (gen_random_uuid(), :g, 'Z', 'x')",
        {"g": group.id},
        "content_version_immutable",
    )
    await _expect_db_error(
        sessions,
        "UPDATE test_versions SET status = 'draft' WHERE id = :id",
        {"id": version.id},
        "content_invalid_transition",
    )
    await _expect_db_error(
        sessions,
        "UPDATE test_versions SET change_note = 'x' WHERE id = :id",
        {"id": version.id},
        "content_version_immutable",
    )
    await _expect_db_error(
        sessions,
        "DELETE FROM test_versions WHERE id = :id",
        {"id": version.id},
        "content_version_immutable",
    )


async def test_drafts_remain_editable(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    draft = await _import_draft(sessions, synthetic_payload(slug=_slug()), licence_id)
    async with sessions() as session, session.begin():
        await session.execute(
            text("UPDATE test_versions SET change_note = 'edited' WHERE id = :id"), {"id": draft.id}
        )
        await session.execute(
            text(
                "UPDATE questions SET difficulty = 'hard' WHERE group_id IN ("
                "SELECT g.id FROM question_groups g JOIN sections s ON s.id = g.section_id "
                "JOIN test_modules m ON m.id = s.test_module_id WHERE m.test_version_id = :id)"
            ),
            {"id": draft.id},
        )


# ----------------------------------------------------------------------------------- constraints
async def test_one_open_version_per_test_is_enforced_by_the_database(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    draft = await _import_draft(sessions, synthetic_payload(slug=_slug()), licence_id)
    async with sessions() as session:
        with pytest.raises(IntegrityError, match="uq_test_versions_one_open"):
            async with session.begin():
                session.add(TestVersion(test_id=draft.test_id, version_no=99, created_by=AUTHOR))


async def test_option_parent_and_marks_constraints(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    draft = await _import_draft(sessions, synthetic_payload(slug=_slug()), licence_id)
    async with sessions() as session:
        tree = await service.load_version_tree(session, draft.id)
    question = tree.modules[0].sections[0].groups[0].questions[0]
    async with sessions() as session:
        with pytest.raises(IntegrityError, match="ck_question_options_exactly_one_parent"):
            async with session.begin():
                session.add(QuestionOption(label="X", text="orphan"))
    async with sessions() as session:
        with pytest.raises(IntegrityError, match="ck_questions_marks_match_numbers"):
            async with session.begin():
                await session.execute(
                    text("UPDATE questions SET marks = 5 WHERE id = :id"), {"id": question.id}
                )


# ----------------------------------------------------------------------------------- read side
async def test_student_view_exposes_no_answers_and_only_published_versions(
    sessions: Sessions,
) -> None:
    _, version = await _published_test(sessions)
    async with sessions() as session:
        view = await content_api.get_student_view(session, version.id)
    serialized = json.dumps(view)
    for forbidden in (
        '"canonical_value"',
        '"variants"',
        '"explanation"',
        '"answer_keys"',
        "the library",
        "Synthetic explanation",
    ):
        assert forbidden not in serialized
    assert len(view["modules"]) == 4
    licence_id = await _licence(sessions)
    draft = await _import_draft(sessions, synthetic_payload(slug=_slug()), licence_id)
    async with sessions() as session:
        with pytest.raises(ContentNotFoundError):
            await content_api.get_student_view(session, draft.id)


async def test_book_full_text_and_trigram_search(sessions: Sessions) -> None:
    licence_id = await _licence(sessions)
    slug = _slug()
    await _import_draft(sessions, synthetic_payload(slug=slug), licence_id)
    async with sessions() as session:
        fts = (
            await session.scalars(
                select(Book.slug).where(
                    Book.search_vector.op("@@")(
                        func.plainto_tsquery("english", "synthetic practice books")
                    )
                )
            )
        ).all()
        fuzzy = (
            await session.scalars(
                select(Book.slug).where(func.similarity(Book.title, "Synthetc Practise Book") > 0.3)
            )
        ).all()
    assert slug in fts
    assert slug in fuzzy


async def test_unpublish_removes_the_test_from_the_library(sessions: Sessions) -> None:
    _, version = await _published_test(sessions)
    async with sessions() as session, session.begin():
        await service.unpublish_version(session, version.id, actor_id=REVIEWER)
    async with sessions() as session:
        refreshed = await session.get_one(TestVersion, version.id)
        test = await session.get_one(Test, version.test_id)
    assert refreshed.status == VersionStatus.ARCHIVED
    assert test.current_published_version_id is None
