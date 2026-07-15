"""Initial schema for Personal AI Runtime.

Creates the complete database structure in a single revision: application
storage tables, the event log (append-only), and Kernel projection tables.
``schema_init.apply_projection_ddl`` re-applies projector-owned table DDL
(timer_events, policy_events, memory_index_repairs) idempotently so the
schema is consistent on both the Alembic and raw-DDL initialization paths.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0001_consolidated"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Application tables ─────────────────────────────────────────────────

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
        sa.Column("conversation_id", sa.Text(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.Text()),
        sa.Column("tool_call_id", sa.Text()),
        sa.Column("source_event_id", sa.Text(), server_default=""),
        sa.Column("sources", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

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
        sa.Column("source_document_id", sa.Text()),
        sa.Column("source_document_name", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("read", sa.Integer(), server_default="0"),
        sa.Column("related_id", sa.Text()),
        sa.Column("related_type", sa.Text()),
        sa.Column("notification_type", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_notifications_related_type",
        "notifications",
        ["related_id", "notification_type"],
        unique=False,
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text()),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

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
        sa.Column("expires_at", sa.DateTime()),
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
        "user_profile",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.5"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("category", name="uq_user_profile_category"),
    )

    op.create_table(
        "inbox_emails",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("server_id", sa.Text()),
        sa.Column("sender", sa.Text()),
        sa.Column("subject", sa.Text()),
        sa.Column("date", sa.Text()),
        sa.Column("preview", sa.Text()),
        sa.Column("full_text", sa.Text()),
        sa.Column("status", sa.Text(), server_default="unread"),
        sa.Column("category", sa.Text()),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("reason", sa.Text()),
        sa.Column("notified", sa.Integer(), server_default="0"),
        sa.Column("digested", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("received_at", sa.DateTime()),
    )

    op.create_table(
        "app_settings",
        sa.Column("category", sa.Text(), primary_key=True),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # ── Kernel tables ──────────────────────────────────────────────────────

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

    # ── Runtime tables ─────────────────────────────────────────────────────

    op.create_table(
        "projection_checkpoints",
        sa.Column("agent_id", sa.Text(), nullable=False, server_default="kernel"),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("last_applied_seq", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("agent_id", "aggregate_type"),
    )

    op.create_table(
        "handler_executions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("handler_name", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("completed_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_handler_executions_status", "handler_executions", ["status"])
    op.create_index("idx_handler_executions_instance", "handler_executions", ["instance_id"])

    op.create_table(
        "work_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("work_type", sa.Text(), server_default="task"),
        sa.Column("parent_work_id", sa.Text()),
        sa.Column("parent_goal_id", sa.Text()),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("dependencies_json", sa.Text()),
        sa.Column("executable_plan", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("progress", sa.Float(), server_default="0"),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("urgency", sa.Float(), server_default="0.5"),
        sa.Column("deadline", sa.Text()),
        sa.Column("last_activity_at", sa.DateTime()),
    )

    # ── Governance projection tables ───────────────────────────────────────

    op.create_table(
        "timer_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("handler_name", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.Text(), nullable=False, server_default="cron"),
        sa.Column("cron_expr", sa.Text(), nullable=False, server_default=""),
        sa.Column("delay_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fire_at", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("payload_json", sa.Text(), server_default="{}"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("fired_at", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("idx_timer_events_status", "timer_events", ["status", "fire_at"])

    op.create_table(
        "policy_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False, server_default="low"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_policy_events_capability", "policy_events", ["capability"])
    op.create_index("idx_policy_events_status", "policy_events", ["status"])

    op.create_table(
        "memory_index_repairs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_retry_at", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_memory_repairs_status", "memory_index_repairs", ["status", "retry_count"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_memory_repairs_status", table_name="memory_index_repairs")
    op.drop_table("memory_index_repairs")
    op.drop_index("idx_policy_events_status", table_name="policy_events")
    op.drop_index("idx_policy_events_capability", table_name="policy_events")
    op.drop_table("policy_events")
    op.drop_index("idx_timer_events_status", table_name="timer_events")
    op.drop_table("timer_events")
    op.drop_table("work_items")
    op.drop_index("idx_handler_executions_instance", table_name="handler_executions")
    op.drop_index("idx_handler_executions_status", table_name="handler_executions")
    op.drop_table("handler_executions")
    op.drop_table("projection_checkpoints")
    op.execute("DROP TRIGGER IF EXISTS event_log_no_delete")
    op.execute("DROP TRIGGER IF EXISTS event_log_no_update")
    op.drop_index("idx_event_log_correlation", table_name="event_log")
    op.drop_index("idx_event_log_aggregate", table_name="event_log")
    op.drop_table("event_log")
    op.drop_table("app_settings")
    op.drop_table("inbox_emails")
    op.drop_table("user_profile")
    op.drop_table("background_tasks")
    op.drop_table("approvals")
    op.drop_table("tool_calls")
    op.drop_table("llm_calls")
    op.drop_table("activity_log")
    op.drop_index("ix_notifications_related_type", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("memories")
    op.drop_table("messages")
    op.drop_table("conversations")
