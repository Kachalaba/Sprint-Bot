"""Create core storage tables"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20240507_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coaches",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "athletes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("team_id", sa.String(length=64), nullable=True),
        sa.Column("coach_id", sa.String(length=64), sa.ForeignKey("coaches.id"), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("pr_5k_seconds", sa.Float(), nullable=True),
        sa.Column("pr_10k_seconds", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "races",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("athlete_id", sa.String(length=64), sa.ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.String(length=64), sa.ForeignKey("coaches.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("distance_meters", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("official_time_seconds", sa.Float(), nullable=True),
        sa.Column("placement_overall", sa.Integer(), nullable=True),
        sa.Column("placement_age_group", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "race_splits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("race_id", sa.String(length=64), sa.ForeignKey("races.id", ondelete="CASCADE"), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heart_rate", sa.Integer(), nullable=True),
        sa.Column("cadence", sa.Integer(), nullable=True),
    )
    op.create_index("ix_race_splits_race_order", "race_splits", ["race_id", "order"], unique=False)

    op.create_table(
        "segment_prs",
        sa.Column("athlete_id", sa.String(length=64), sa.ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("segment_id", sa.String(length=64), primary_key=True),
        sa.Column("best_time_seconds", sa.Float(), nullable=False),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("race_id", sa.String(length=64), sa.ForeignKey("races.id"), nullable=True),
    )

    op.create_table(
        "sum_of_bests",
        sa.Column("athlete_id", sa.String(length=64), sa.ForeignKey("athletes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("total_time_seconds", sa.Float(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sum_of_bests")
    op.drop_table("segment_prs")
    op.drop_index("ix_race_splits_race_order", table_name="race_splits")
    op.drop_table("race_splits")
    op.drop_table("races")
    op.drop_table("athletes")
    op.drop_table("coaches")
