"""Telegram: привязка чата, журнал откликов, уведомления

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_linked_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("telegram_link_code_hash", sa.String(length=64)))
    op.add_column("users", sa.Column("telegram_link_expires_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(op.f("uq_users_telegram_chat_id"), "users", ["telegram_chat_id"])
    op.create_unique_constraint(
        op.f("uq_users_telegram_link_code_hash"), "users", ["telegram_link_code_hash"]
    )

    op.create_table(
        "applications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_applications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_applications_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("user_id", "vacancy_id", name=op.f("uq_applications_user_id")),
    )
    op.create_index("ix_applications_vacancy_id", "applications", ["vacancy_id"])

    op.create_table(
        "status_history",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        _timestamp("changed_at"),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_status_history_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_status_history")),
    )
    op.create_index("ix_status_history_application_id", "status_history", ["application_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_notifications_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_notifications_idempotency_key")),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_status_history_application_id", table_name="status_history")
    op.drop_table("status_history")
    op.drop_index("ix_applications_vacancy_id", table_name="applications")
    op.drop_table("applications")
    op.drop_constraint(op.f("uq_users_telegram_link_code_hash"), "users", type_="unique")
    op.drop_constraint(op.f("uq_users_telegram_chat_id"), "users", type_="unique")
    op.drop_column("users", "telegram_link_expires_at")
    op.drop_column("users", "telegram_link_code_hash")
    op.drop_column("users", "telegram_linked_at")
