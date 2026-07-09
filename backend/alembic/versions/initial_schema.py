"""Initial schema — all application and kernel tables.

Single consolidated baseline for fresh installs.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Application tables ---

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
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

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
        sa.Column("parent_id", sa.Text(), sa.ForeignKey("goals.id")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_activity_at", sa.DateTime()),
    )

    op.create_table(
        "actions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("goal_id", sa.Text(), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("executable_plan", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime()),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("goal_id", sa.Text(), sa.ForeignKey("goals.id")),
        sa.Column("payload", sa.Text()),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
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
        "tasks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("parent_goal_id", sa.Text(), sa.ForeignKey("goals.id")),
        sa.Column("parent_task_id", sa.Text(), sa.ForeignKey("tasks.id")),
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("dependencies_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
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
        sa.UniqueConstraint("category", name="uq_user_profile_category"),
    )

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
        sa.Column("status", sa.Text(), server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "app_settings",
        sa.Column("category", sa.Text(), primary_key=True),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # --- Kernel tables ---

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

    # --- Runtime tables (Phase 4: Execution Model) ---

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


def downgrade() -> None:
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
    op.drop_table("patterns")
    op.drop_table("user_profile")
    op.drop_table("triggers")
    op.drop_table("background_tasks")
    op.drop_table("approvals")
    op.drop_table("tool_calls")
    op.drop_table("llm_calls")
    op.drop_table("tasks")
    op.drop_table("activity_log")
    op.drop_table("schedules")
    op.drop_table("notifications")
    op.drop_table("memories")
    op.drop_table("events")
    op.drop_table("actions")
    op.drop_table("goals")
    op.drop_table("messages")
    op.drop_table("conversations")
