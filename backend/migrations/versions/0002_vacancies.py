"""Источники, вакансии, критерии поиска, результаты фильтра

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_ARRAY = sa.text("'{}'")


def upgrade() -> None:
    sources = op.create_table(
        "sources",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("last_run_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_sources")),
    )
    op.bulk_insert(sources, [{"code": "getmatch"}])

    op.create_table(
        "vacancies",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_code", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("salary_from", sa.Integer(), nullable=True),
        sa.Column("salary_to", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=True),
        sa.Column("salary_gross", sa.Boolean(), nullable=True),
        sa.Column(
            "work_formats",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column(
            "contract_types",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("description_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_code"],
            ["sources.code"],
            name=op.f("fk_vacancies_source_code_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancies")),
        sa.UniqueConstraint(
            "source_code",
            "external_id",
            name=op.f("uq_vacancies_source_code"),
        ),
    )

    op.create_table(
        "search_profiles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "title_keywords",
            postgresql.ARRAY(sa.Text()),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column(
            "stop_words",
            postgresql.ARRAY(sa.Text()),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("min_salary", sa.Integer(), nullable=True),
        sa.Column("min_salary_is_net", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("remote_only", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "contract_types",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_search_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_search_profiles_user_id")),
    )

    op.create_table(
        "vacancy_filter_results",
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=EMPTY_ARRAY,
            nullable=False,
        ),
        sa.Column("salary_unknown", sa.Boolean(), nullable=False),
        sa.Column(
            "filtered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_vacancy_filter_results_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_vacancy_filter_results_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vacancy_id", "user_id", name=op.f("pk_vacancy_filter_results")),
    )


def downgrade() -> None:
    op.drop_table("vacancy_filter_results")
    op.drop_table("search_profiles")
    op.drop_table("vacancies")
    op.drop_table("sources")
