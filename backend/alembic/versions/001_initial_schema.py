"""Initial migration — create all application tables.

Combines:
  - database.py SCHEMA_SQL (19 tables)
  - kernel.py EVENT_LOG_SCHEMA (event_log)
  - trajectory_links (dropped in migration 002)
  - kernel.py ALTER TABLE additions (memories columns)

Revision ID: 001
Revises: None
Create Date: 2026-06-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Application tables (from database.py SCHEMA_SQL) ---

    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.Text()),
        sa.Column("tool_call_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_foreign_key("fk_messages_conv", "messages", "conversations", ["conversation_id"], ["id"])

    op.create_table(
        "goals",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.Text(), server_default="active"),
        sa.Column("progress", sa.Float(), server_default="0.0"),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("urgency", sa.Float(), server_default="0.5"),
        sa.Column("deadline", sa.DateTime()),
        sa.Column("parent_id", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_activity_at", sa.DateTime()),
    )
    op.create_foreign_key("fk_goals_parent", "goals", "goals", ["parent_id"], ["id"])

    op.create_table(
        "actions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("goal_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("executable_plan", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime()),
    )
    op.create_foreign_key("fk_actions_goal", "actions", "goals", ["goal_id"], ["id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("goal_id", sa.Text()),
        sa.Column("payload", sa.Text()),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_foreign_key("fk_events_goal", "events", "goals", ["goal_id"], ["id"])

    op.create_table(
        "memories",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text()),
        sa.Column("embedding_id", sa.Text()),
        sa.Column("confidence", sa.Float(), server_default="0.5"),
        sa.Column("derived_from_event", sa.Text()),
        sa.Column("decayed_at", sa.DateTime()),
        sa.Column("status", sa.Text(), server_default="active"),
        sa.Column("origin", sa.Text(), server_default="claim"),
        sa.Column("claim_status", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "reviews",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("key_insights", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("read", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cron_expr", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), server_default="cron"),
        sa.Column("trigger_config", sa.Text()),
        sa.Column("config", sa.Text()),
        sa.Column("enabled", sa.Integer(), server_default="1"),
        sa.Column("last_run_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text()),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("chunk_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("parent_goal_id", sa.Text()),
        sa.Column("parent_task_id", sa.Text()),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("dependencies_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_foreign_key("fk_tasks_goal", "tasks", "goals", ["parent_goal_id"], ["id"])
    op.create_foreign_key("fk_tasks_parent", "tasks", "tasks", ["parent_task_id"], ["id"])

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), server_default="0"),
        sa.Column("latency_ms", sa.Float(), server_default="0"),
        sa.Column("cost", sa.Float(), server_default="0"),
        sa.Column("success", sa.Integer(), server_default="1"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("success", sa.Integer(), server_default="1"),
        sa.Column("latency_ms", sa.Float(), server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("task_id", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("params", sa.Text()),
        sa.Column("proposed_by", sa.Text()),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolved_by", sa.Text()),
    )

    op.create_table(
        "background_tasks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("plan_json", sa.Text()),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("progress", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime()),
    )

    op.create_table(
        "triggers",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("condition_json", sa.Text(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_config", sa.Text()),
        sa.Column("enabled", sa.Integer(), server_default="1"),
        sa.Column("last_fired_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "user_profile",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.5"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_unique_constraint("uq_user_profile_category", "user_profile", ["category"])

    op.create_table(
        "patterns",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("pattern_type", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("statistics", sa.Text(), nullable=False),
        sa.Column("evidence_chain", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "inbox_emails",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("sender", sa.Text()),
        sa.Column("subject", sa.Text()),
        sa.Column("preview", sa.Text()),
        sa.Column("received_at", sa.DateTime()),
        sa.Column("category", sa.Text()),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("reason", sa.Text()),
        sa.Column("notified", sa.Integer(), server_default="0"),
        sa.Column("digested", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # --- Kernel tables (from kernel.py EVENT_LOG_SCHEMA) ---

    op.create_table(
        "event_log",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.Text(), nullable=False, unique=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False, server_default="system"),
        sa.Column("payload", sa.Text()),
        sa.Column("caused_by", sa.Text()),
        sa.Column("correlation_id", sa.Text()),
        sa.Column("ts", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_event_log_aggregate", "event_log", ["aggregate_type", "aggregate_id", "seq"])
    op.create_index("idx_event_log_correlation", "event_log", ["correlation_id"])

    # Event log immutability triggers
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS event_log_no_update
            BEFORE UPDATE ON event_log
            BEGIN SELECT RAISE(ABORT, 'event_log is append-only: UPDATE forbidden'); END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS event_log_no_delete
            BEFORE DELETE ON event_log
            BEGIN SELECT RAISE(ABORT, 'event_log is append-only: DELETE forbidden'); END
    """)

    # --- Trajectory links (from kernel.py TRAJECTORY_LINKS_SCHEMA) ---

    op.create_table(
        "trajectory_links",
        sa.Column("link_id", sa.Text(), primary_key=True),
        sa.Column("trajectory_id", sa.Text(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("claim_status", sa.Text(), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("rationale", sa.Text()),
        sa.Column("actor", sa.Text(), nullable=False, server_default="system"),
        sa.Column("linked_at_seq", sa.Integer()),
        sa.Column("linked_at", sa.Text()),
        sa.Column("updated_at", sa.Text()),
    )
    op.create_index("idx_trajectory_links_trajectory", "trajectory_links", ["trajectory_id", "linked_at_seq"])


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS event_log_no_update")
    op.execute("DROP TRIGGER IF EXISTS event_log_no_delete")
    op.drop_table("trajectory_links")
    op.drop_table("event_log")
    op.drop_table("inbox_emails")
    op.drop_table("patterns")
    op.drop_table("user_profile")
    op.drop_table("triggers")
    op.drop_table("background_tasks")
    op.drop_table("approvals")
    op.drop_table("tool_calls")
    op.drop_table("llm_calls")
    op.drop_table("tasks")
    op.drop_table("documents")
    op.drop_table("activity_log")
    op.drop_table("schedules")
    op.drop_table("notifications")
    op.drop_table("reviews")
    op.drop_table("memories")
    op.drop_table("events")
    op.drop_table("actions")
    op.drop_table("goals")
    op.drop_table("messages")
    op.drop_table("conversations")
