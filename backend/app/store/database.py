"""SQLite database management — connection pool + schema lifecycle.

Governed reads go through Kernel.query_state; this class owns only:
  1. Connection pool (thread-local, WAL mode, busy_timeout)
  2. Schema lifecycle (Alembic or raw DDL in constructor)
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from app.config import settings

logger = logging.getLogger(__name__)
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
        except BaseException:
            # GeneratorExit / KeyboardInterrupt are not Exception subclasses.
            # Still rollback so a TLS connection does not keep a sticky BEGIN
            # and serve a stale WAL snapshot on later reuse.
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        # Connection is kept open for reuse; closed only on explicit close().

    def get_raw_connection(self) -> sqlite3.Connection:
        """Return a **new**, independent connection (not from the TLS pool).

        Callers are responsible for calling .commit(), .rollback(), and
        .close() on the returned connection.  This is intended for
        long-running atomic operations that must not share the thread-local
        transaction scope (e.g. import_event_log_rows).
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

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

    # --- Activity log (APP_STORAGE, not governed) ---

    def log_activity(self, activity_type: str, payload: str | None = None):
        with self.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES (?, ?)",
                (activity_type, payload),
            )


from app.core.runtime.runtime_container import _LazyProxy, runtime  # noqa: E402

if TYPE_CHECKING:
    db: Database
else:
    db = _LazyProxy(lambda: runtime.db)
