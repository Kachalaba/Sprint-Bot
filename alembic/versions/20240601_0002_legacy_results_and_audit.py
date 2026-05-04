"""Create legacy results, result_segments, turn_analysis and audit_log tables.

These tables originally lived in per-service SQLite databases and were
created via inline ``CREATE TABLE IF NOT EXISTS`` statements scattered
across the legacy services. This migration brings them under Alembic so
the same schema is reproducible in the Postgres backend.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20240601_0002"
down_revision = "20240507_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("athlete_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("stroke", sa.Text(), nullable=False),
        sa.Column("distance", sa.Integer(), nullable=False),
        sa.Column("total_seconds", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.Text(), nullable=False),
        sa.Column(
            "is_pr",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("turn_times", sa.Text(), nullable=True),
        sa.Column("approach_times", sa.Text(), nullable=True),
        sa.Column("underwater_times", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_results_athlete_timestamp",
        "results",
        ["athlete_id", "timestamp"],
    )

    op.create_table(
        "result_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "result_id",
            sa.Integer(),
            sa.ForeignKey("results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("split_seconds", sa.Float(), nullable=False),
    )
    op.create_index(
        "idx_result_segments_result", "result_segments", ["result_id"]
    )
    op.create_index(
        "idx_result_segments_lookup",
        "result_segments",
        ["result_id", "segment_index"],
    )

    op.create_table(
        "turn_analysis",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "result_id",
            sa.Integer(),
            sa.ForeignKey("results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("approach_time", sa.Float(), nullable=True),
        sa.Column("wall_contact_time", sa.Float(), nullable=True),
        sa.Column("push_off_time", sa.Float(), nullable=True),
        sa.Column("underwater_time", sa.Float(), nullable=True),
        sa.Column("total_turn_time", sa.Float(), nullable=True),
    )
    op.create_index(
        "idx_turn_analysis_result_id", "turn_analysis", ["result_id"]
    )
    op.create_index(
        "idx_turn_analysis_result_turn",
        "turn_analysis",
        ["result_id", "turn_number"],
    )
    op.create_index(
        "idx_turn_analysis_turn_number", "turn_analysis", ["turn_number"]
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("ts", sa.Text(), nullable=False),
    )
    op.create_index("idx_audit_log_ts", "audit_log", [sa.text("ts DESC")])
    op.create_index(
        "idx_audit_log_entity", "audit_log", ["entity_type", "entity_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_audit_log_entity", table_name="audit_log")
    op.drop_index("idx_audit_log_ts", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("idx_turn_analysis_turn_number", table_name="turn_analysis")
    op.drop_index("idx_turn_analysis_result_turn", table_name="turn_analysis")
    op.drop_index("idx_turn_analysis_result_id", table_name="turn_analysis")
    op.drop_table("turn_analysis")

    op.drop_index("idx_result_segments_lookup", table_name="result_segments")
    op.drop_index("idx_result_segments_result", table_name="result_segments")
    op.drop_table("result_segments")

    op.drop_index("ix_results_athlete_timestamp", table_name="results")
    op.drop_table("results")
