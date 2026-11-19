"""Create the content schema (Phase 5a): licences, media metadata, catalogue, versioned test
trees, question items, reviews, imports and band-conversion structure.

Generated with `alembic revision --autogenerate` against a scratch database, then reviewed:
the `tests` <-> `test_versions` foreign-key cycle is created after both tables exist and dropped
before either table on downgrade.

Content data is irreplaceable: downgrade is for test databases only and needs explicit approval
anywhere else (docs/DATABASE_SCHEMA.md §10).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "band_conversion_tables",
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("variant", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "module IN ('listening', 'reading')", name=op.f("ck_band_conversion_tables_module")
        ),
        sa.CheckConstraint(
            "variant IN ('academic', 'general', 'common')",
            name=op.f("ck_band_conversion_tables_variant"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_band_conversion_tables")),
    )
    op.create_index(
        "uq_band_conversion_tables_one_default",
        "band_conversion_tables",
        ["module", "variant"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_table(
        "content_licenses",
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("licensor", sa.String(length=200), nullable=False),
        sa.Column("licence_reference", sa.String(length=200), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column(
            "terms", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("post_lapse_access", sa.String(length=20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "post_lapse_access IS NULL OR post_lapse_access IN ('keep_review', 'scores_only', 'remove')",
            name=op.f("ck_content_licenses_post_lapse_access"),
        ),
        sa.CheckConstraint(
            "source_type IN ('original', 'licensed', 'public_domain', 'user_generated')",
            name=op.f("ck_content_licenses_source_type"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_from <= valid_until",
            name=op.f("ck_content_licenses_validity_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_licenses")),
    )
    op.create_table(
        "question_types",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("family", sa.String(length=30), nullable=False),
        sa.Column("modules", sa.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("handler_version", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_question_types")),
    )
    op.create_table(
        "band_conversion_rows",
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("raw_min", sa.Integer(), nullable=False),
        sa.Column("raw_max", sa.Integer(), nullable=False),
        sa.Column("band", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.CheckConstraint(
            "band >= 0 AND band <= 9 AND band * 2 = floor(band * 2)",
            name=op.f("ck_band_conversion_rows_band"),
        ),
        sa.CheckConstraint(
            "raw_min >= 0 AND raw_min <= raw_max", name=op.f("ck_band_conversion_rows_raw_range")
        ),
        sa.ForeignKeyConstraint(
            ["table_id"],
            ["band_conversion_tables.id"],
            name=op.f("fk_band_conversion_rows_table_id_band_conversion_tables"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("table_id", "raw_min", name=op.f("pk_band_conversion_rows")),
    )
    op.create_table(
        "media_assets",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="uploading", nullable=False),
        sa.Column("license_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('audio', 'image', 'document')", name=op.f("ck_media_assets_kind")
        ),
        sa.CheckConstraint(
            "status IN ('uploading', 'processing', 'ready', 'failed')",
            name=op.f("ck_media_assets_status"),
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0", name=op.f("ck_media_assets_size_non_negative")
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["content_licenses.id"],
            name=op.f("fk_media_assets_license_id_content_licenses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_media_assets_storage_key")),
    )
    op.create_table(
        "books",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("series", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("license_id", sa.Uuid(), nullable=False),
        sa.Column("cover_asset_id", sa.Uuid(), nullable=True),
        sa.Column("is_premium", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(series, '') || ' ' || coalesce(description, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cover_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_books_cover_asset_id_media_assets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["content_licenses.id"],
            name=op.f("fk_books_license_id_content_licenses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_books")),
        sa.UniqueConstraint("slug", name=op.f("uq_books_slug")),
    )
    op.create_index(
        "ix_books_search_vector", "books", ["search_vector"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_books_title_trgm",
        "books",
        ["title"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_table(
        "book_editions",
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("edition_label", sa.String(length=100), nullable=False),
        sa.Column("publication_year", sa.Integer(), nullable=True),
        sa.Column("variant", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "variant IN ('academic', 'general', 'both')", name=op.f("ck_book_editions_variant")
        ),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_book_editions_book_id_books"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_editions")),
        sa.UniqueConstraint(
            "book_id", "edition_label", name=op.f("uq_book_editions_book_id_edition_label")
        ),
    )
    op.create_table(
        "tests",
        sa.Column("edition_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_published_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["edition_id"],
            ["book_editions.id"],
            name=op.f("fk_tests_edition_id_book_editions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tests")),
        sa.UniqueConstraint("edition_id", "code", name=op.f("uq_tests_edition_id_code")),
    )
    op.create_table(
        "test_versions",
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'in_review', 'published', 'archived')",
            name=op.f("ck_test_versions_status"),
        ),
        sa.CheckConstraint("version_no >= 1", name=op.f("ck_test_versions_version_no_positive")),
        sa.ForeignKeyConstraint(
            ["test_id"], ["tests.id"], name="fk_test_versions_test_id_tests", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_versions")),
        sa.UniqueConstraint(
            "test_id", "version_no", name=op.f("uq_test_versions_test_id_version_no")
        ),
    )
    # Close the tests <-> test_versions cycle now that both tables exist.
    op.create_foreign_key(
        "fk_tests_current_published_version_id_test_versions",
        "tests",
        "test_versions",
        ["current_published_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_test_versions_one_open",
        "test_versions",
        ["test_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'in_review')"),
    )
    op.create_index(
        "uq_test_versions_one_published",
        "test_versions",
        ["test_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_table(
        "content_reviews",
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved', 'changes_requested')",
            name=op.f("ck_content_reviews_decision"),
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_content_reviews_test_version_id_test_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_reviews")),
    )
    op.create_table(
        "import_jobs",
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_format", sa.String(length=10), server_default="json", nullable=False),
        sa.Column("file_name", sa.String(length=300), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("license_id", sa.Uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "summary", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("result_test_version_id", sa.Uuid(), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("source_format IN ('json')", name=op.f("ck_import_jobs_source_format")),
        sa.CheckConstraint(
            "status IN ('validated', 'failed', 'committed')", name=op.f("ck_import_jobs_status")
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["content_licenses.id"],
            name=op.f("fk_import_jobs_license_id_content_licenses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["result_test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_import_jobs_result_test_version_id_test_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_jobs")),
    )
    op.create_table(
        "test_modules",
        sa.Column("test_version_id", sa.Uuid(), nullable=False),
        sa.Column("module", sa.String(length=20), nullable=False),
        sa.Column("variant", sa.String(length=20), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "module IN ('listening', 'reading', 'writing', 'speaking')",
            name=op.f("ck_test_modules_module"),
        ),
        sa.CheckConstraint(
            "variant IN ('academic', 'general', 'common')", name=op.f("ck_test_modules_variant")
        ),
        sa.ForeignKeyConstraint(
            ["test_version_id"],
            ["test_versions.id"],
            name=op.f("fk_test_modules_test_version_id_test_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_modules")),
        sa.UniqueConstraint(
            "test_version_id",
            "module",
            "variant",
            name=op.f("uq_test_modules_test_version_id_module_variant"),
        ),
    )
    op.create_table(
        "import_job_issues",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "severity IN ('error', 'warning')", name=op.f("ck_import_job_issues_severity")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["import_jobs.id"],
            name=op.f("fk_import_job_issues_job_id_import_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_job_issues")),
    )
    op.create_table(
        "sections",
        sa.Column("test_module_id", sa.Uuid(), nullable=False),
        sa.Column("section_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("audio_asset_id", sa.Uuid(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audio_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_sections_audio_asset_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_module_id"],
            ["test_modules.id"],
            name=op.f("fk_sections_test_module_id_test_modules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint(
            "test_module_id", "section_no", name=op.f("uq_sections_test_module_id_section_no")
        ),
    )
    op.create_table(
        "speaking_parts",
        sa.Column("test_module_id", sa.Uuid(), nullable=False),
        sa.Column("part_no", sa.Integer(), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("cue_card", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("part_no IN (1, 2, 3)", name=op.f("ck_speaking_parts_part_no")),
        sa.ForeignKeyConstraint(
            ["test_module_id"],
            ["test_modules.id"],
            name=op.f("fk_speaking_parts_test_module_id_test_modules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_parts")),
        sa.UniqueConstraint(
            "test_module_id", "part_no", name=op.f("uq_speaking_parts_test_module_id_part_no")
        ),
    )
    op.create_table(
        "writing_tasks",
        sa.Column("test_module_id", sa.Uuid(), nullable=True),
        sa.Column("task_no", sa.Integer(), nullable=False),
        sa.Column("task_kind", sa.String(length=30), nullable=False),
        sa.Column("prompt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("image_asset_id", sa.Uuid(), nullable=True),
        sa.Column("min_words", sa.Integer(), nullable=False),
        sa.Column(
            "key_features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "task_kind IN ('academic_report', 'gt_letter', 'essay')",
            name=op.f("ck_writing_tasks_task_kind"),
        ),
        sa.CheckConstraint("min_words > 0", name=op.f("ck_writing_tasks_min_words_positive")),
        sa.CheckConstraint("task_no IN (1, 2)", name=op.f("ck_writing_tasks_task_no")),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_writing_tasks_image_asset_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["test_module_id"],
            ["test_modules.id"],
            name=op.f("fk_writing_tasks_test_module_id_test_modules"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_writing_tasks")),
    )
    op.create_table(
        "passages",
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("title", sa.String(length=300), nullable=True),
        sa.Column(
            "body_format", sa.String(length=20), server_default="prosemirror_json", nullable=False
        ),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "body_format IN ('prosemirror_json', 'markdown')", name=op.f("ck_passages_body_format")
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_passages_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passages")),
    )
    op.create_table(
        "question_groups",
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("image_asset_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["image_asset_id"],
            ["media_assets.id"],
            name=op.f("fk_question_groups_image_asset_id_media_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["question_type"],
            ["question_types.code"],
            name=op.f("fk_question_groups_question_type_question_types"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["sections.id"],
            name=op.f("fk_question_groups_section_id_sections"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_groups")),
    )
    op.create_table(
        "sample_answers",
        sa.Column("writing_task_id", sa.Uuid(), nullable=True),
        sa.Column("speaking_part_id", sa.Uuid(), nullable=True),
        sa.Column("band", sa.Numeric(precision=2, scale=1), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("license_id", sa.Uuid(), nullable=False),
        sa.Column("author_note", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "band IS NULL OR (band >= 0 AND band <= 9 AND band * 2 = floor(band * 2))",
            name=op.f("ck_sample_answers_band_half_steps"),
        ),
        sa.CheckConstraint(
            "num_nonnulls(writing_task_id, speaking_part_id) = 1",
            name=op.f("ck_sample_answers_exactly_one_target"),
        ),
        sa.ForeignKeyConstraint(
            ["license_id"],
            ["content_licenses.id"],
            name=op.f("fk_sample_answers_license_id_content_licenses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["speaking_part_id"],
            ["speaking_parts.id"],
            name=op.f("fk_sample_answers_speaking_part_id_speaking_parts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["writing_task_id"],
            ["writing_tasks.id"],
            name=op.f("fk_sample_answers_writing_task_id_writing_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sample_answers")),
    )
    op.create_table(
        "speaking_questions",
        sa.Column("speaking_part_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_follow_up", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["speaking_part_id"],
            ["speaking_parts.id"],
            name=op.f("fk_speaking_questions_speaking_part_id_speaking_parts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_speaking_questions")),
    )
    op.create_table(
        "paragraphs",
        sa.Column("passage_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=10), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("plain_text", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["passages.id"],
            name=op.f("fk_paragraphs_passage_id_passages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_paragraphs")),
    )
    op.create_table(
        "questions",
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("lineage_id", sa.Uuid(), nullable=False),
        sa.Column("number_from", sa.Integer(), nullable=False),
        sa.Column("number_to", sa.Integer(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("stem", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("difficulty", sa.String(length=10), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.String(length=50)), server_default="{}", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "difficulty IS NULL OR difficulty IN ('easy', 'medium', 'hard')",
            name=op.f("ck_questions_difficulty"),
        ),
        sa.CheckConstraint(
            "marks = number_to - number_from + 1", name=op.f("ck_questions_marks_match_numbers")
        ),
        sa.CheckConstraint(
            "number_from >= 1 AND number_from <= number_to", name=op.f("ck_questions_number_range")
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["question_groups.id"],
            name=op.f("fk_questions_group_id_question_groups"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_index(
        "ix_questions_group_number", "questions", ["group_id", "number_from"], unique=False
    )
    op.create_index(op.f("ix_questions_lineage_id"), "questions", ["lineage_id"], unique=False)
    op.create_table(
        "answer_keys",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("canonical_value", sa.Text(), nullable=False),
        sa.Column("notation", sa.Text(), nullable=True),
        sa.Column("match_mode", sa.String(length=20), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "match_mode IN ('text', 'option', 'set_member', 'numeric', 'time', 'date')",
            name=op.f("ck_answer_keys_match_mode"),
        ),
        sa.CheckConstraint("slot >= 1", name=op.f("ck_answer_keys_slot_positive")),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_answer_keys_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_keys")),
        sa.UniqueConstraint("question_id", "slot", name=op.f("uq_answer_keys_question_id_slot")),
    )
    op.create_table(
        "explanations",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_paragraph_id", sa.Uuid(), nullable=True),
        sa.Column("audio_start_ms", sa.Integer(), nullable=True),
        sa.Column("audio_end_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_paragraph_id"],
            ["paragraphs.id"],
            name=op.f("fk_explanations_evidence_paragraph_id_paragraphs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_explanations_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_explanations")),
        sa.UniqueConstraint("question_id", name=op.f("uq_explanations_question_id")),
    )
    op.create_table(
        "question_options",
        sa.Column("question_id", sa.Uuid(), nullable=True),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(question_id, group_id) = 1",
            name=op.f("ck_question_options_exactly_one_parent"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["question_groups.id"],
            name=op.f("fk_question_options_group_id_question_groups"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_options_question_id_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_options")),
    )
    op.create_table(
        "answer_variants",
        sa.Column("answer_key_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["answer_key_id"],
            ["answer_keys.id"],
            name=op.f("fk_answer_variants_answer_key_id_answer_keys"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answer_variants")),
        sa.UniqueConstraint(
            "answer_key_id", "value", name=op.f("uq_answer_variants_answer_key_id_value")
        ),
    )


def downgrade() -> None:
    # Required. If irreversible, raise NotImplementedError and explain why (DATABASE_SCHEMA.md §10).
    op.drop_table("answer_variants")
    op.drop_table("question_options")
    op.drop_table("explanations")
    op.drop_table("answer_keys")
    op.drop_index(op.f("ix_questions_lineage_id"), table_name="questions")
    op.drop_index("ix_questions_group_number", table_name="questions")
    op.drop_table("questions")
    op.drop_table("paragraphs")
    op.drop_table("speaking_questions")
    op.drop_table("sample_answers")
    op.drop_table("question_groups")
    op.drop_table("passages")
    op.drop_table("writing_tasks")
    op.drop_table("speaking_parts")
    op.drop_table("sections")
    op.drop_table("import_job_issues")
    op.drop_table("test_modules")
    op.drop_table("import_jobs")
    op.drop_table("content_reviews")
    op.drop_index(
        "uq_test_versions_one_published",
        table_name="test_versions",
        postgresql_where=sa.text("status = 'published'"),
    )
    op.drop_index(
        "uq_test_versions_one_open",
        table_name="test_versions",
        postgresql_where=sa.text("status IN ('draft', 'in_review')"),
    )
    op.drop_constraint(
        "fk_tests_current_published_version_id_test_versions", "tests", type_="foreignkey"
    )
    op.drop_table("test_versions")
    op.drop_table("tests")
    op.drop_table("book_editions")
    op.drop_index(
        "ix_books_title_trgm",
        table_name="books",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.drop_index("ix_books_search_vector", table_name="books", postgresql_using="gin")
    op.drop_table("books")
    op.drop_table("media_assets")
    op.drop_table("band_conversion_rows")
    op.drop_table("question_types")
    op.drop_table("content_licenses")
    op.drop_index(
        "uq_band_conversion_tables_one_default",
        table_name="band_conversion_tables",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_table("band_conversion_tables")
