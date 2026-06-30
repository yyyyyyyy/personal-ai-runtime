"""SQLite database management with Alembic-powered schema initialization."""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

# Thread-local connection cache to avoid per-call connection overhead.
# Each Database path gets its own SQLite connection per thread; the connection
# is reused across get_db() calls within the same thread and cleaned up on close().
# Keyed by db_path to prevent cross-Database connection reuse in tests.
_tls = threading.local()


def _tls_connections() -> dict[str, sqlite3.Connection]:
    """Return (creating if needed) the per-thread connection dict."""
    d = getattr(_tls, "connections", None)
    if d is None:
        d = {}
        _tls.connections = d
    return d


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        # Set durable pragmas once at startup (WAL mode is a DB property)
        self._ensure_wal_pragmas()

    def _ensure_wal_pragmas(self) -> None:
        """Apply persistent pragmas that only need to run once per DB file."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            # WAL + NORMAL synchronous: durability is guaranteed by WAL,
            # fsync on every commit is unnecessary overhead.
            conn.execute("PRAGMA synchronous=NORMAL")
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Ensure schema via shared init (Alembic on production DB, raw DDL elsewhere)."""
        from app.store.schema_init import ensure_schema

        ensure_schema(self)

    def _get_connection(self) -> sqlite3.Connection:
        # Check if there's an open connection for this db_path in the current thread.
        connections = _tls_connections()
        conn = connections.get(self.db_path)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            connections[self.db_path] = conn
        return conn

    def close(self):
        """Close the thread-local connection for this db_path, if any."""
        connections = _tls_connections()
        conn = connections.pop(self.db_path, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    @contextmanager
    def get_db(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            logger.exception("Database transaction rolled back")
            conn.rollback()
            raise
        # Connection is kept open for reuse; closed only on explicit close().

    # --- Conversation methods (read-only; writes go through ConversationAPI) ---

    def get_conversation(self, conv_id: str) -> dict | None:
        with self.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, limit: int = 50) -> list[dict]:
        with self.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Message methods (read-only; writes go through ConversationManager) ---

    def get_message(self, msg_id: str) -> dict | None:
        with self.get_db() as conn:
            row = conn.execute(
                "SELECT * FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_recent_messages(self, conv_id: str, limit: int = 50) -> list[dict]:
        with self.get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
                (conv_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- WAL checkpoint — call periodically to keep the WAL file bounded ---

    def wal_checkpoint(self, mode: str = "PASSIVE") -> None:
        """Run a WAL checkpoint to truncate the -wal sidecar file.

        PASSIVE is safe to call at any time without blocking readers/writers.
        """
        conn = self._get_connection()
        try:
            conn.execute(f"PRAGMA wal_checkpoint({mode})")
        except Exception:
            logger.debug("WAL checkpoint failed", exc_info=True)

    # --- Activity log ---

    def log_activity(self, activity_type: str, payload: str | None = None):
        with self.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES (?, ?)",
                (activity_type, payload),
            )


db = Database()
