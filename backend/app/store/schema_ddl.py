"""Raw SQL DDL for non-Alembic database initialization (tests and fallback)."""

APP_STORAGE_DDL = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    progress REAL DEFAULT 0,
    importance REAL DEFAULT 0.5,
    urgency REAL DEFAULT 0.5,
    deadline TEXT,
    parent_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    tool_call_id TEXT,
    source_event_id TEXT,
    sources TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    related_id TEXT,
    related_type TEXT,
    notification_type TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    payload TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

# v0.5.0: unified work_items table supersedes tasks + actions.
# Must be executed in ALL paths (raw DDL + Alembic) because Alembic
# migrations don't include this table yet.
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
    -- v1.0 Goal→Work unification: goal-specific fields (Phase 1, additive).
    -- Existing rows get sane defaults; goal rows (work_type='goal') populate them.
    progress REAL DEFAULT 0,
    importance REAL DEFAULT 0.5,
    urgency REAL DEFAULT 0.5,
    deadline TEXT,
    last_activity_at DATETIME
);
"""

APP_STORAGE_DDL_TAIL = """
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

CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    success INTEGER DEFAULT 1,
    latency_ms REAL DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS background_tasks (
    id TEXT PRIMARY KEY,
    user_request TEXT NOT NULL,
    plan_json TEXT,
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS triggers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_config TEXT,
    enabled INTEGER DEFAULT 1,
    last_fired_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    data_json TEXT,
    confidence REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    category TEXT PRIMARY KEY,
    data_json TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    type TEXT,
    payload TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    goal_id TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS email_settings (
    provider TEXT DEFAULT 'gmail',
    user TEXT,
    password TEXT,
    imap_host TEXT,
    smtp_host TEXT
);
"""

EVENT_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS event_log (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    id        TEXT    UNIQUE NOT NULL,
    type      TEXT    NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT '',
    aggregate_id   TEXT NOT NULL DEFAULT '',
    actor     TEXT    NOT NULL DEFAULT 'system',
    payload   TEXT    NOT NULL DEFAULT '{}',
    caused_by       TEXT    DEFAULT NULL,
    correlation_id  TEXT    DEFAULT NULL,
    ts        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_log_aggregate
    ON event_log (aggregate_type, aggregate_id);
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
    agent_id        TEXT    NOT NULL,
    aggregate_type  TEXT    NOT NULL,
    last_applied_seq INTEGER NOT NULL DEFAULT 0,
    snapshot_json   TEXT    NOT NULL DEFAULT '{}',
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
    policy_json   TEXT    DEFAULT NULL,
    correlation_id TEXT   DEFAULT '',
    created_at    TEXT    DEFAULT NULL,
    started_at    TEXT    DEFAULT NULL,
    completed_at  TEXT    DEFAULT NULL,
    error         TEXT    DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_handler_executions_status
    ON handler_executions (status);
CREATE INDEX IF NOT EXISTS idx_handler_executions_instance
    ON handler_executions (instance_id);
"""

TIMER_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS timer_events (
    id            TEXT PRIMARY KEY,
    handler_name  TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    cron_expr     TEXT,
    delay_seconds INTEGER,
    fire_at       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'active',
    created_at    TEXT DEFAULT NULL,
    fired_at      TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_timer_events_status_fire
    ON timer_events (status, fire_at);
"""

POLICY_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_events (
    id          TEXT PRIMARY KEY,
    capability  TEXT NOT NULL,
    risk_level  TEXT NOT NULL DEFAULT 'low',
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_policy_events_capability
    ON policy_events (capability);
CREATE INDEX IF NOT EXISTS idx_policy_events_status
    ON policy_events (status);
"""

GRANT_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS grant_events (
    id               TEXT PRIMARY KEY,
    principal_id     TEXT NOT NULL,
    capability       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active',
    created_at       TEXT NOT NULL,
    revoked_at       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_grant_events_principal
    ON grant_events (principal_id);
CREATE INDEX IF NOT EXISTS idx_grant_events_capability
    ON grant_events (principal_id, capability);
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

MEMORIES_LEGACY_DDL = [
    "ALTER TABLE memories ADD COLUMN confidence REAL DEFAULT 0.5",
    "ALTER TABLE memories ADD COLUMN derived_from_event TEXT",
    "ALTER TABLE memories ADD COLUMN decayed_at DATETIME",
    "ALTER TABLE memories ADD COLUMN status TEXT DEFAULT 'active'",
    "ALTER TABLE memories ADD COLUMN origin TEXT DEFAULT 'claim'",
    "ALTER TABLE memories ADD COLUMN claim_status TEXT",
    "ALTER TABLE memories ADD COLUMN source_document_id TEXT",
    "ALTER TABLE memories ADD COLUMN source_document_name TEXT",
]
