"""Raw SQL DDL for non-Alembic database initialization (tests and fallback).

This module is the single source of truth for inline DDL. Kernel projectors
must not own parallel CREATE TABLE strings — import from here if needed.
"""

CONVERSATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    tool_call_id TEXT,
    source_event_id TEXT DEFAULT '',
    sources TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
"""

NOTIFICATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    related_id TEXT,
    related_type TEXT,
    notification_type TEXT,
    dedup_key TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_notifications_related_type 
    ON notifications (related_id, notification_type);
CREATE INDEX IF NOT EXISTS ix_notifications_dedup_key 
    ON notifications (dedup_key);
"""

ACTIVITY_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    payload TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

MEMORIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    embedding_id TEXT,
    confidence REAL DEFAULT 0.5,
    derived_from_event TEXT,
    decayed_at DATETIME,
    status TEXT DEFAULT 'active',
    origin TEXT DEFAULT 'claim',
    claim_status TEXT,
    source_document_id TEXT,
    source_document_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# Unified work_items table (Goal / Task / Action are work_type values).
WORK_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    work_type TEXT DEFAULT 'task',
    parent_work_id TEXT,
    parent_goal_id TEXT,
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    dependencies_json TEXT,
    executable_plan TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    progress REAL DEFAULT 0,
    importance REAL DEFAULT 0.5,
    urgency REAL DEFAULT 0.5,
    deadline TEXT,
    last_activity_at DATETIME
);
"""

LLM_CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    cost REAL DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created_at ON llm_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_model ON llm_calls (model);
"""

TOOL_CALLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    success INTEGER DEFAULT 1,
    latency_ms REAL DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created_at ON tool_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_name ON tool_calls (tool_name);
"""

APPROVALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    action TEXT NOT NULL,
    params TEXT,
    proposed_by TEXT,
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    resolved_at DATETIME,
    resolved_by TEXT
);
"""

BACKGROUND_TASKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS background_tasks (
    id TEXT PRIMARY KEY,
    user_request TEXT NOT NULL,
    plan_json TEXT,
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);
"""

USER_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profile (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    data_json TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category)
);
"""

APP_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    category TEXT PRIMARY KEY,
    data_json TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

INBOX_EMAILS_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox_emails (
    id TEXT PRIMARY KEY,
    server_id TEXT,
    sender TEXT,
    subject TEXT,
    date TEXT,
    preview TEXT,
    full_text TEXT,
    status TEXT DEFAULT 'unread',
    category TEXT,
    importance REAL DEFAULT 0.5,
    reason TEXT,
    notified INTEGER DEFAULT 0,
    digested INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    received_at DATETIME
);
"""

EVENT_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_log (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    id        TEXT    UNIQUE NOT NULL,
    type      TEXT    NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id   TEXT NOT NULL,
    actor     TEXT    NOT NULL DEFAULT 'system',
    payload   TEXT,
    caused_by       TEXT,
    correlation_id  TEXT,
    ts        DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_log_aggregate
    ON event_log (aggregate_type, aggregate_id, seq);
CREATE INDEX IF NOT EXISTS idx_event_log_correlation
    ON event_log (correlation_id);

CREATE TRIGGER IF NOT EXISTS event_log_no_update
    BEFORE UPDATE ON event_log
    BEGIN SELECT RAISE(ABORT, 'event_log is append-only: UPDATE forbidden'); END;
CREATE TRIGGER IF NOT EXISTS event_log_no_delete
    BEFORE DELETE ON event_log
    BEGIN SELECT RAISE(ABORT, 'event_log is append-only: DELETE forbidden'); END;
"""

PROJECTION_CHECKPOINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS projection_checkpoints (
    agent_id        TEXT    NOT NULL DEFAULT 'kernel',
    aggregate_type  TEXT    NOT NULL,
    last_applied_seq INTEGER NOT NULL,
    snapshot_json   TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (agent_id, aggregate_type)
);
"""

HANDLER_EXECUTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS handler_executions (
    id            TEXT PRIMARY KEY,
    event_seq     INTEGER NOT NULL,
    event_id      TEXT    NOT NULL,
    event_type    TEXT    NOT NULL,
    handler_name  TEXT    NOT NULL,
    instance_id   TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    retry_count   INTEGER NOT NULL DEFAULT 0,
    policy_json   TEXT    NOT NULL DEFAULT '{}',
    correlation_id TEXT   NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    started_at    TEXT    NOT NULL DEFAULT '',
    completed_at  TEXT    NOT NULL DEFAULT '',
    error         TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_handler_executions_status
    ON handler_executions (status);
CREATE INDEX IF NOT EXISTS idx_handler_executions_instance
    ON handler_executions (instance_id);
"""

TIMER_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS timer_events (
    id               TEXT PRIMARY KEY,
    handler_name     TEXT NOT NULL,
    schedule_type    TEXT NOT NULL DEFAULT 'cron',
    cron_expr        TEXT NOT NULL DEFAULT '',
    delay_seconds    REAL NOT NULL DEFAULT 0,
    fire_at          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'active',
    payload_json     TEXT DEFAULT '{}',
    created_at       TEXT NOT NULL,
    fired_at         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_timer_events_status
    ON timer_events (status, fire_at);
"""

POLICY_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_events (
    id               TEXT PRIMARY KEY,
    capability       TEXT NOT NULL,
    risk_level       TEXT NOT NULL DEFAULT 'low',  -- low | high | forbidden
    status           TEXT NOT NULL DEFAULT 'active',  -- active | revoked
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_events_capability
    ON policy_events (capability);
CREATE INDEX IF NOT EXISTS idx_policy_events_status
    ON policy_events (status);
"""

MEMORY_INDEX_REPAIRS_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_index_repairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregate_id    TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    event_seq       INTEGER NOT NULL,
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    last_retry_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_memory_repairs_status
    ON memory_index_repairs (status, retry_count);
"""

# Ordered list of all schemas for full database initialization.
ALL_SCHEMAS = [
    CONVERSATIONS_SCHEMA,
    MESSAGES_SCHEMA,
    MEMORIES_SCHEMA,
    NOTIFICATIONS_SCHEMA,
    ACTIVITY_LOG_SCHEMA,
    LLM_CALLS_SCHEMA,
    TOOL_CALLS_SCHEMA,
    APPROVALS_SCHEMA,
    BACKGROUND_TASKS_SCHEMA,
    USER_PROFILE_SCHEMA,
    INBOX_EMAILS_SCHEMA,
    APP_SETTINGS_SCHEMA,
    EVENT_LOG_SCHEMA,
    PROJECTION_CHECKPOINTS_SCHEMA,
    HANDLER_EXECUTIONS_SCHEMA,
    WORK_ITEMS_SCHEMA,
    TIMER_EVENTS_SCHEMA,
    POLICY_EVENTS_SCHEMA,
    MEMORY_INDEX_REPAIRS_SCHEMA,
]
