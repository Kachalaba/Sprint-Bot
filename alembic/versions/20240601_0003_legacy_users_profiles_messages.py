"""Create legacy users, trainer_athletes, user_profiles, messages tables.

Brings the bot's auxiliary SQLite databases (roles.db, users.db, chat
data) under Alembic control so the same schema is reproducible in
Postgres deployments.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20240601_0003"
down_revision = "20240601_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("full_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("role", sa.Text(), nullable=False, server_default="athlete"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_telegram_users_role", "telegram_users", ["role"])

    op.create_table(
        "trainer_athletes",
        sa.Column(
            "athlete_id",
            sa.BigInteger(),
            sa.ForeignKey("telegram_users.telegram_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "trainer_id",
            sa.BigInteger(),
            sa.ForeignKey("telegram_users.telegram_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_trainer_athletes_trainer", "trainer_athletes", ["trainer_id"]
    )

    op.create_table(
        "user_profiles",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=False, server_default="uk"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trainer_id", sa.BigInteger(), nullable=False),
        sa.Column("athlete_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column(
            "read_by_trainer",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "read_by_athlete",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index("idx_messages_trainer", "messages", ["trainer_id"])
    op.create_index("idx_messages_athlete", "messages", ["athlete_id"])
    op.create_index(
        "idx_messages_pair",
        "messages",
        ["trainer_id", "athlete_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_messages_pair", table_name="messages")
    op.drop_index("idx_messages_athlete", table_name="messages")
    op.drop_index("idx_messages_trainer", table_name="messages")
    op.drop_table("messages")

    op.drop_table("user_profiles")

    op.drop_index("ix_trainer_athletes_trainer", table_name="trainer_athletes")
    op.drop_table("trainer_athletes")

    op.drop_index("ix_telegram_users_role", table_name="telegram_users")
    op.drop_table("telegram_users")
