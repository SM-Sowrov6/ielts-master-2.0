"""Database-level immutability of published content (defence in depth, ADR-007).

- `test_versions`: only legal lifecycle transitions; non-lifecycle columns change only while
  `draft`; published/archived versions cannot be deleted.
- Every table inside a version tree: INSERT/UPDATE/DELETE is rejected when the owning version is
  `published` or `archived`. Rows whose owner cannot be resolved (e.g. standalone writing tasks,
  or rows being removed by the cascade delete of a draft) are allowed.

Errors use SQLSTATE 'P0001' with a message starting `content_version_immutable` /
`content_invalid_transition`, which the service layer maps to domain errors.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Table -> SQL returning the owning test_version id for a row exposed as JSONB `r`.
_MODULE = "(SELECT tm.test_version_id FROM test_modules tm WHERE tm.id = {col})"
_SECTION = (
    "(SELECT tm.test_version_id FROM sections s JOIN test_modules tm ON tm.id = s.test_module_id "
    "WHERE s.id = {col})"
)
_GROUP = (
    "(SELECT tm.test_version_id FROM question_groups g JOIN sections s ON s.id = g.section_id "
    "JOIN test_modules tm ON tm.id = s.test_module_id WHERE g.id = {col})"
)
_QUESTION = (
    "(SELECT tm.test_version_id FROM questions q JOIN question_groups g ON g.id = q.group_id "
    "JOIN sections s ON s.id = g.section_id JOIN test_modules tm ON tm.id = s.test_module_id "
    "WHERE q.id = {col})"
)


def _uuid(field: str) -> str:
    return f"(r->>'{field}')::uuid"


OWNER_SQL: dict[str, str] = {
    "test_modules": _uuid("test_version_id"),
    "sections": _MODULE.format(col=_uuid("test_module_id")),
    "writing_tasks": _MODULE.format(col=_uuid("test_module_id")),
    "speaking_parts": _MODULE.format(col=_uuid("test_module_id")),
    "speaking_questions": (
        "(SELECT tm.test_version_id FROM speaking_parts sp "
        "JOIN test_modules tm ON tm.id = sp.test_module_id "
        f"WHERE sp.id = {_uuid('speaking_part_id')})"
    ),
    "passages": _SECTION.format(col=_uuid("section_id")),
    "question_groups": _SECTION.format(col=_uuid("section_id")),
    "paragraphs": (
        "(SELECT tm.test_version_id FROM passages p JOIN sections s ON s.id = p.section_id "
        "JOIN test_modules tm ON tm.id = s.test_module_id "
        f"WHERE p.id = {_uuid('passage_id')})"
    ),
    "questions": _GROUP.format(col=_uuid("group_id")),
    "question_options": (
        f"COALESCE({_QUESTION.format(col=_uuid('question_id'))}, "
        f"{_GROUP.format(col=_uuid('group_id'))})"
    ),
    "answer_keys": _QUESTION.format(col=_uuid("question_id")),
    "explanations": _QUESTION.format(col=_uuid("question_id")),
    "answer_variants": (
        "(SELECT tm.test_version_id FROM answer_keys k JOIN questions q ON q.id = k.question_id "
        "JOIN question_groups g ON g.id = q.group_id JOIN sections s ON s.id = g.section_id "
        "JOIN test_modules tm ON tm.id = s.test_module_id "
        f"WHERE k.id = {_uuid('answer_key_id')})"
    ),
}


def _owner_function() -> str:
    branches = "\n".join(
        f"    WHEN '{table}' THEN RETURN {sql};" for table, sql in OWNER_SQL.items()
    )
    return f"""
CREATE OR REPLACE FUNCTION content_owning_version(tbl text, r jsonb) RETURNS uuid
LANGUAGE plpgsql STABLE AS $$
BEGIN
  CASE tbl
{branches}
    ELSE RAISE EXCEPTION 'content_owning_version: unknown table %', tbl;
  END CASE;
END $$;
"""


GUARD_TREE = """
CREATE OR REPLACE FUNCTION content_guard_tree() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_status text;
  rec jsonb;
BEGIN
  FOREACH rec IN ARRAY (CASE TG_OP
      WHEN 'INSERT' THEN ARRAY[to_jsonb(NEW)]
      WHEN 'DELETE' THEN ARRAY[to_jsonb(OLD)]
      ELSE ARRAY[to_jsonb(OLD), to_jsonb(NEW)] END)
  LOOP
    SELECT status INTO v_status FROM test_versions
      WHERE id = content_owning_version(TG_TABLE_NAME, rec);
    IF v_status IN ('published', 'archived') THEN
      RAISE EXCEPTION 'content_version_immutable: % on % belongs to a % version',
        TG_OP, TG_TABLE_NAME, v_status USING ERRCODE = 'P0001';
    END IF;
  END LOOP;
  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
"""

GUARD_VERSION = """
CREATE OR REPLACE FUNCTION content_guard_test_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('published', 'archived') THEN
      RAISE EXCEPTION 'content_version_immutable: cannot delete a % version', OLD.status
        USING ERRCODE = 'P0001';
    END IF;
    RETURN OLD;
  END IF;

  IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
       (OLD.status = 'draft' AND NEW.status = 'in_review')
    OR (OLD.status = 'in_review' AND NEW.status IN ('draft', 'published'))
    OR (OLD.status = 'published' AND NEW.status = 'archived')
  ) THEN
    RAISE EXCEPTION 'content_invalid_transition: % -> %', OLD.status, NEW.status
      USING ERRCODE = 'P0001';
  END IF;

  -- Outside draft, only lifecycle columns may change.
  IF OLD.status <> 'draft' AND (
       NEW.test_id IS DISTINCT FROM OLD.test_id
    OR NEW.version_no IS DISTINCT FROM OLD.version_no
    OR NEW.change_note IS DISTINCT FROM OLD.change_note
    OR NEW.created_by IS DISTINCT FROM OLD.created_by
    OR NEW.created_at IS DISTINCT FROM OLD.created_at
  ) THEN
    RAISE EXCEPTION 'content_version_immutable: % version fields are read-only', OLD.status
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;
"""


def upgrade() -> None:
    op.execute(_owner_function())
    op.execute(GUARD_TREE)
    op.execute(GUARD_VERSION)
    op.execute(
        "CREATE TRIGGER trg_test_versions_guard BEFORE UPDATE OR DELETE ON test_versions "
        "FOR EACH ROW EXECUTE FUNCTION content_guard_test_version()"
    )
    for table in OWNER_SQL:
        op.execute(
            f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION content_guard_tree()"
        )


def downgrade() -> None:
    for table in OWNER_SQL:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_guard ON {table}")
    op.execute("DROP TRIGGER IF EXISTS trg_test_versions_guard ON test_versions")
    op.execute("DROP FUNCTION IF EXISTS content_guard_test_version()")
    op.execute("DROP FUNCTION IF EXISTS content_guard_tree()")
    op.execute("DROP FUNCTION IF EXISTS content_owning_version(text, jsonb)")
