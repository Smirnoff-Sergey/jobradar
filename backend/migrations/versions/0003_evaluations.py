"""Резюме, LLM-оценки, дневной счётчик запросов к LLM

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
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
        "resumes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_resumes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resumes")),
    )
    op.create_index(
        "uq_resumes_user_id_active",
        "resumes",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )

    op.create_table(
        "evaluations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("resume_id", sa.BigInteger(), nullable=False),
        sa.Column("prompt_version", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column("verdict", sa.String(length=8), nullable=True),
        sa.Column("matches", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gaps", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dealbreakers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
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
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_evaluations_resume_id_resumes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_evaluations_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluations")),
        sa.UniqueConstraint(
            "vacancy_id",
            "resume_id",
            "prompt_version",
            name=op.f("uq_evaluations_vacancy_id"),
        ),
    )

    op.create_index("ix_evaluations_resume_id", "evaluations", ["resume_id"])

    op.create_table(
        "llm_daily_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_llm_daily_usage")),
    )

    op.create_table(
        "llm_guard",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("paused_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_guard")),
    )


def downgrade() -> None:
    op.drop_table("llm_guard")
    op.drop_table("llm_daily_usage")
    op.drop_index("ix_evaluations_resume_id", table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index("uq_resumes_user_id_active", table_name="resumes")
    op.drop_table("resumes")
