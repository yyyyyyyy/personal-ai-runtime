"""Explicit registry of governed projection tables vs application storage tables.

Every business table in SQLite must appear in exactly one of these sets.
New tables must be classified here or schema contract tests will fail.
"""

from __future__ import annotations

# Kernel-owned projections (event-sourced read models + event log).
GOVERNED_TABLES: frozenset[str] = frozenset({
    "event_log",
    "work_items",  # v1.0: unified task + action + goal projection
    "memories",
    "approvals",
    "conversations",
    "messages",
    "notifications",
    "projection_checkpoints",
    "handler_executions",
    "timer_events",
    "policy_events",
    # v0.3.0: promoted from APP_STORAGE — derived solely from InboxEmail* events
    # via projectors_inbox.py so the table is fully rebuildable from event_log.
    "inbox_emails",
    # v0.3.0: promoted from APP_STORAGE — derived solely from Capability* events
    # via projectors_telemetry.py. Every row maps 1:1 to a CapabilityInvoked,
    # CapabilityFailed, or CapabilityDenied event in event_log.
    "tool_calls",
    # v0.3.0: promoted from APP_STORAGE — derived solely from LLMCallRecorded
    # events via projectors_telemetry.py.
    "llm_calls",
})

# Application storage (direct read/write outside Kernel ABI is allowed).
#
# Why each of these is NOT event-sourced (North Star P8 / NG6):
# The Truth Layer (event_log + GOVERNED_TABLES above) is event-sourced because
# it represents authoritative personal facts whose loss would break data
# sovereignty. The tables below are operational/observational and either (a)
# can be regenerated from authoritative sources, (b) are pure caches, or
# (c) hold app-local config with no audit requirement. They must never be
# presented as a second source of truth.
APP_STORAGE_TABLES: frozenset[str] = frozenset({
    # Human-readable activity log; derived from event_log via projection.
    "activity_log",
    # Background task queue state; lifecycle is governed by BackgroundTask*
    # events in event_log. This table is a worker-scratch view.
    "background_tasks",
    # User profile / app settings — local-only preferences. No audit value;
    # exporting event_log is sufficient for data sovereignty.
    "user_profile",
    # App settings (UI preferences, LLM/Email connection config). Local-only
    # operational config; not a governed fact.
    "app_settings",
    # Pending ChromaDB index repairs for memory events whose embedding sync
    # failed. The authoritative record is the MemoryDerived/Updated event in
    # event_log; this queue tracks outstanding reconciliation work and is
    # drained by RuntimeLoop._maintenance via the memory index repair worker.
    "memory_index_repairs",
})

# Expected columns for governed projection tables (PRAGMA contract).
GOVERNED_SCHEMA: dict[str, frozenset[str]] = {
    "work_items": frozenset({  # v1.0: unified task + action + goal
        "id", "title", "description", "work_type", "parent_work_id",
        "parent_goal_id", "status", "priority", "dependencies_json",
        "executable_plan", "created_at", "updated_at", "completed_at",
        # v1.0 goal-unification columns (work_type='goal' rows populate these):
        "progress", "importance", "urgency", "deadline", "last_activity_at",
    }),
    "memories": frozenset({
        "id", "category", "content", "source", "embedding_id", "created_at",
        "confidence", "derived_from_event", "decayed_at", "status", "origin",
        "claim_status", "source_document_id", "source_document_name",
    }),
    "approvals": frozenset({
        "id", "task_id", "action", "params", "proposed_by", "status",
        "created_at", "expires_at", "resolved_at", "resolved_by",
    }),
    "conversations": frozenset({
        "id", "title", "summary", "created_at", "updated_at",
    }),
    "messages": frozenset({
        "id", "conversation_id", "role", "content", "tool_calls", "tool_call_id",
        "created_at", "source_event_id", "sources",
    }),
    "notifications": frozenset({
        "id", "type", "title", "content", "read",
        "related_id", "related_type", "notification_type", "created_at",
    }),
    "event_log": frozenset({
        "seq", "id", "type", "aggregate_type", "aggregate_id", "actor", "payload",
        "caused_by", "correlation_id", "ts",
    }),
    "projection_checkpoints": frozenset({
        "agent_id", "aggregate_type", "last_applied_seq", "snapshot_json", "created_at",
    }),
    "handler_executions": frozenset({
        "id", "event_seq", "event_id", "event_type", "handler_name",
        "instance_id", "status", "retry_count", "policy_json",
        "correlation_id", "created_at", "started_at", "completed_at", "error",
    }),
    "timer_events": frozenset({
        "id", "handler_name", "schedule_type", "cron_expr", "delay_seconds",
        "fire_at", "status", "payload_json", "created_at", "fired_at",
    }),
    "policy_events": frozenset({
        "id", "capability", "risk_level", "status", "created_at", "updated_at",
    }),
    "inbox_emails": frozenset({
        "id", "server_id", "sender", "subject", "date", "preview",
        "full_text", "status", "category", "importance", "reason",
        "notified", "digested", "created_at", "received_at",
    }),
    "tool_calls": frozenset({
        "id", "tool_name", "success", "latency_ms", "error_message", "created_at",
    }),
    "llm_calls": frozenset({
        "id", "provider", "model", "prompt_tokens", "completion_tokens",
        "latency_ms", "cost", "success", "error_message", "created_at",
    }),
}

ALL_CLASSIFIED_TABLES = GOVERNED_TABLES | APP_STORAGE_TABLES
