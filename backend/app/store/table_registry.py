"""Explicit registry of governed projection tables vs application storage tables.

Every business table in SQLite must appear in exactly one of these sets.
New tables must be classified here or schema contract tests will fail.
"""

from __future__ import annotations

# Kernel-owned projections (event-sourced read models + event log).
GOVERNED_TABLES: frozenset[str] = frozenset({
    "event_log",
    "goals",
    "actions",
    "tasks",
    "memories",
    "approvals",
    "patterns",
    "trajectory_links",
    "conversations",
    "messages",
    "projection_checkpoints",
})

# Application storage (direct read/write outside Kernel ABI is allowed).
APP_STORAGE_TABLES: frozenset[str] = frozenset({
    "events",
    "reviews",
    "notifications",
    "schedules",
    "activity_log",
    "documents",
    "llm_calls",
    "tool_calls",
    "background_tasks",
    "triggers",
    "user_profile",
    "inbox_emails",
})

# Expected columns for governed projection tables (PRAGMA contract).
GOVERNED_SCHEMA: dict[str, frozenset[str]] = {
    "goals": frozenset({
        "id", "title", "description", "status", "progress", "importance", "urgency",
        "deadline", "parent_id", "created_at", "updated_at", "last_activity_at",
    }),
    "actions": frozenset({
        "id", "goal_id", "title", "status", "executable_plan", "created_at", "completed_at",
    }),
    "tasks": frozenset({
        "id", "name", "description", "parent_goal_id", "parent_task_id", "status",
        "priority", "dependencies_json", "created_at", "updated_at",
    }),
    "memories": frozenset({
        "id", "category", "content", "source", "embedding_id", "created_at",
        "confidence", "derived_from_event", "decayed_at", "status", "origin",
        "claim_status",
    }),
    "approvals": frozenset({
        "id", "task_id", "action", "params", "proposed_by", "status",
        "created_at", "resolved_at", "resolved_by",
    }),
    "patterns": frozenset({
        "id", "pattern_type", "metric", "window_days", "statistics",
        "evidence_chain", "created_at",
    }),
    "trajectory_links": frozenset({
        "link_id", "trajectory_id", "event_seq", "claim_status", "confidence",
        "rationale", "actor", "linked_at_seq", "linked_at", "updated_at",
    }),
    "conversations": frozenset({
        "id", "title", "summary", "created_at", "updated_at",
    }),
    "messages": frozenset({
        "id", "conversation_id", "role", "content", "tool_calls", "tool_call_id",
        "created_at",
    }),
    "event_log": frozenset({
        "seq", "id", "type", "aggregate_type", "aggregate_id", "actor", "payload",
        "caused_by", "correlation_id", "ts",
    }),
    "projection_checkpoints": frozenset({
        "aggregate_type", "last_applied_seq", "snapshot_json", "created_at",
    }),
}

ALL_CLASSIFIED_TABLES = GOVERNED_TABLES | APP_STORAGE_TABLES
