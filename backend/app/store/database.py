"""SQLite database management with Alembic-powered schema initialization."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.sqlite_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Ensure schema via shared init (Alembic on production DB, raw DDL elsewhere)."""
        from app.store.schema_init import ensure_schema

        ensure_schema(self)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

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
        finally:
            conn.close()

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

    # --- Activity log ---

    def log_activity(self, activity_type: str, payload: str | None = None):
        with self.get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (type, payload) VALUES (?, ?)",
                (activity_type, payload),
            )


db = Database()
