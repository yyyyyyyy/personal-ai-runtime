# mypy: disable-error-code="attr-defined"
"""Kernel Query State Mixin — read-only projection queries.

Extracted from kernel.py to keep the main module focused on the write ABI
(emit_event / invoke_capability / task lifecycle).
"""

from __future__ import annotations

from typing import Any


class QueryStateMixin:  # type: ignore[attr-defined]  # mixed into Kernel which provides _db
    """Read layer: query_state and projection table accessors."""

    def query_state(self, selector: str, **filters: Any) -> list[dict]:
        """Read current State (a projection). Returns list of dict rows."""
        if selector == "goals":
            return self._query_goals(filters)
        if selector == "work_items":  # unified task + action + trigger
            return self._query_work_items(filters)
        if selector == "approvals":
            return self._query_approvals(filters)
        if selector == "memories":
            return self._query_memories(filters)
        if selector == "notifications":
            return self._query_notifications(filters)
        if selector == "timer_events":
            return self._query_timer_events(filters)
        if selector == "policy_events":
            return self._query_policy_events(filters)
        if selector == "conversations":
            return self._query_conversations(filters)
        if selector == "messages":
            return self._query_messages(filters)
        if selector == "inbox_emails":
            return self._query_inbox_emails(filters)
        if selector == "background_tasks":
            return self._query_background_tasks(filters)
        if selector == "user_profile":
            return self._query_user_profile(filters)
        raise ValueError(f"Unknown state selector: {selector!r}")

    def _query_goals(self, filters: dict[str, Any]) -> list[dict]:
        goal_id = filters.get("id")
        status = filters.get("status")
        status_in = filters.get("status_in")
        limit = filters.get("limit", 50)
        order = filters.get("order", "importance_desc")
        last_activity_older_than_days = filters.get("last_activity_older_than_days")
        deadline_within_days = filters.get("deadline_within_days")
        updated_since = filters.get("updated_since")
        has_deadline = filters.get("has_deadline")

        order_clauses = {
            "importance_desc": "importance DESC, created_at DESC",
            "importance_urgency_desc": "importance DESC, urgency DESC",
            "last_activity_asc": "last_activity_at ASC",
            "importance_desc_only": "importance DESC",
        }
        order_sql = order_clauses.get(order, order_clauses["importance_desc"])

        with self._db.get_db() as conn:
            if goal_id:
                row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status_in is not None:
                placeholders = ",".join("?" * len(status_in))
                clauses.append(f"status IN ({placeholders})")
                params.extend(status_in)
            elif status is not None:
                clauses.append("status = ?")
                params.append(status)
            if last_activity_older_than_days is not None:
                clauses.append("last_activity_at < datetime('now', ?)")
                params.append(f"-{int(last_activity_older_than_days)} days")
            if deadline_within_days is not None:
                clauses.append(
                    "deadline IS NOT NULL AND deadline BETWEEN datetime('now') AND datetime('now', ?)"
                )
                params.append(f"+{int(deadline_within_days)} days")
            if updated_since is not None:
                clauses.append("updated_at >= ?")
                params.append(updated_since)
            if has_deadline:
                clauses.append("deadline IS NOT NULL")

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM goals{where} ORDER BY {order_sql} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_work_items(self, filters: dict[str, Any]) -> list[dict]:
        """Unified query for work_items table (v0.5.0: supersedes tasks+actions)."""
        item_id = filters.get("id")
        status = filters.get("status")
        work_type = filters.get("work_type")
        parent_goal_id = filters.get("parent_goal_id")
        parent_work_id = filters.get("parent_work_id")
        root_only = filters.get("root_only")
        depends_on_work = filters.get("depends_on_work")
        limit = filters.get("limit", 50)
        order = filters.get("order", "created_at_asc")

        order_clauses = {
            "created_at_asc": "created_at ASC",
            "created_at_desc": "created_at DESC",
            "priority_desc": "priority DESC, created_at ASC",
        }
        order_sql = order_clauses.get(order, order_clauses["created_at_asc"])

        with self._db.get_db() as conn:
            if item_id:
                row = conn.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if work_type is not None:
                clauses.append("work_type = ?")
                params.append(work_type)
            if parent_goal_id is not None:
                clauses.append("parent_goal_id = ?")
                params.append(parent_goal_id)
            if parent_work_id is not None:
                clauses.append("parent_work_id = ?")
                params.append(parent_work_id)
            if root_only:
                clauses.append("parent_work_id IS NULL")
            if depends_on_work is not None:
                clauses.append("dependencies_json LIKE ?")
                params.append(f"%{depends_on_work}%")

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(int(limit))
            rows = conn.execute(
                f"SELECT * FROM work_items{where} ORDER BY {order_sql} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_approvals(self, filters: dict[str, Any]) -> list[dict]:
        approval_id = filters.get("id")
        status = filters.get("status")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if approval_id:
                row = conn.execute(
                    "SELECT * FROM approvals WHERE id = ?", (approval_id,)
                ).fetchone()
                return [dict(row)] if row else []
            if status is not None:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def _query_memories(self, filters: dict[str, Any]) -> list[dict]:
        memory_id = filters.get("id")
        category = filters.get("category")
        origin = filters.get("origin")
        claim_status = filters.get("claim_status")
        confidence_gt = filters.get("confidence_gt")
        confidence_lt = filters.get("confidence_lt")
        decay_eligible = filters.get("decay_eligible")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if memory_id:
                row = conn.execute(
                    "SELECT * FROM memories WHERE id = ?", (memory_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if category is not None:
                clauses.append("category = ?")
                params.append(category)
            if origin is not None:
                clauses.append("origin = ?")
                params.append(origin)
            if claim_status is not None:
                clauses.append("claim_status = ?")
                params.append(claim_status)
            if confidence_gt is not None:
                clauses.append("confidence > ?")
                params.append(confidence_gt)
            if confidence_lt is not None:
                clauses.append("confidence < ?")
                params.append(confidence_lt)
            if decay_eligible:
                clauses.append(
                    "(decayed_at IS NULL OR decayed_at < datetime('now', '-7 days'))"
                )

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM memories{where} ORDER BY confidence DESC, created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_notifications(self, filters: dict[str, Any]) -> list[dict]:
        notification_id = filters.get("id")
        notif_type = filters.get("type")
        title = filters.get("title")
        unread_only = filters.get("unread_only")
        created_on_date = filters.get("created_on_date")
        related_id = filters.get("related_id")
        notification_type = filters.get("notification_type")
        limit = filters.get("limit", 50)
        order = filters.get("order", "created_at_desc")

        order_clauses = {
            "created_at_desc": "created_at DESC",
            "created_at_asc": "created_at ASC",
        }
        order_sql = order_clauses.get(order, order_clauses["created_at_desc"])

        with self._db.get_db() as conn:
            if notification_id:
                row = conn.execute(
                    "SELECT * FROM notifications WHERE id = ?", (notification_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if notif_type is not None:
                clauses.append("type = ?")
                params.append(notif_type)
            if title is not None:
                clauses.append("title = ?")
                params.append(title)
            if unread_only:
                clauses.append("read = 0")
            if created_on_date is not None:
                clauses.append("date(created_at) = date(?)")
                params.append(created_on_date)
            if related_id is not None:
                clauses.append("related_id = ?")
                params.append(related_id)
            if notification_type is not None:
                clauses.append("notification_type = ?")
                params.append(notification_type)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM notifications{where} ORDER BY {order_sql} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def list_capability_definitions(self) -> list[dict]:
        """Read-only capability metadata for LLM tool schemas (User Space ABI)."""
        from app.core.harness.mcp_hub import mcp_hub

        return mcp_hub.get_tool_defs_for_llm()

    def recall_memory(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from derived memories (projected from MemoryDerived events)."""
        from app.store.vector import vector_store

        return vector_store.search_memories(query, n_results=k)

    def recall_knowledge(self, query: str, k: int = 5) -> list[dict]:
        """Semantic recall from knowledge base documents."""
        from app.store.vector import vector_store

        return vector_store.search_knowledge(query, n_results=k)

    def _query_conversations(self, filters: dict[str, Any]) -> list[dict]:
        conv_id = filters.get("id")
        limit = filters.get("limit", 50)
        order = filters.get("order", "created_at_desc")

        order_sql = "updated_at DESC" if order == "created_at_desc" else "created_at ASC"
        with self._db.get_db() as conn:
            if conv_id:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE id = ?", (conv_id,)
                ).fetchone()
                return [dict(row)] if row else []
            rows = conn.execute(
                f"SELECT * FROM conversations ORDER BY {order_sql} LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_messages(self, filters: dict[str, Any]) -> list[dict]:
        conversation_id = filters.get("conversation_id")
        limit = filters.get("limit", 20)
        order = filters.get("order", "created_at_desc")

        if not conversation_id:
            return []

        order_clauses = {
            "created_at_desc": "created_at DESC",
            "created_at_asc": "created_at ASC",
        }
        order_sql = order_clauses.get(order, order_clauses["created_at_desc"])

        with self._db.get_db() as conn:
            rows = conn.execute(
                f"""SELECT * FROM messages
                    WHERE conversation_id = ?
                    ORDER BY {order_sql}
                    LIMIT ?""",
                (conversation_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_inbox_emails(self, filters: dict[str, Any]) -> list[dict]:
        email_id = filters.get("id")
        status_not = filters.get("status_not")
        search = filters.get("search")
        limit = filters.get("limit", 20)
        order = filters.get("order", "date_desc")

        order_clauses = {
            "date_desc": "COALESCE(received_at, created_at) DESC",
            "date_asc": "COALESCE(received_at, created_at) ASC",
            "created_at_desc": "created_at DESC",
        }
        order_sql = order_clauses.get(order, order_clauses["date_desc"])

        with self._db.get_db() as conn:
            if email_id:
                row = conn.execute(
                    "SELECT * FROM inbox_emails WHERE id = ?", (email_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status_not is not None:
                clauses.append("status != ?")
                params.append(status_not)
            if search:
                clauses.append(
                    "(subject LIKE ? OR sender LIKE ? OR preview LIKE ?)"
                )
                pattern = f"%{search}%"
                params.extend([pattern, pattern, pattern])

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f'SELECT * FROM inbox_emails{where} ORDER BY {order_sql} LIMIT ?',
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_timer_events(self, filters: dict[str, Any]) -> list[dict]:
        timer_id = filters.get("id")
        status = filters.get("status")
        fire_at_lt = filters.get("fire_at_lt")
        limit = filters.get("limit", 50)

        with self._db.get_db() as conn:
            if timer_id:
                row = conn.execute(
                    "SELECT * FROM timer_events WHERE id = ?",
                    (timer_id,),
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)
            if fire_at_lt is not None:
                clauses.append("fire_at <= ? AND fire_at != ''")
                params.append(fire_at_lt)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM timer_events{where} ORDER BY fire_at ASC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_policy_events(self, filters: dict[str, Any]) -> list[dict]:
        capability = filters.get("capability")
        status = filters.get("status")
        limit = filters.get("limit", 200)

        with self._db.get_db() as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if capability is not None:
                clauses.append("capability = ?")
                params.append(capability)
            if status is not None:
                clauses.append("status = ?")
                params.append(status)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM policy_events{where} ORDER BY capability ASC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_background_tasks(self, filters: dict[str, Any]) -> list[dict]:
        task_id = filters.get("id")
        status = filters.get("status")
        limit = filters.get("limit", 50)
        order = filters.get("order", "created_at_desc")

        order_clause = "created_at DESC" if order == "created_at_desc" else "created_at ASC"

        with self._db.get_db() as conn:
            if task_id:
                row = conn.execute(
                    "SELECT * FROM background_tasks WHERE id = ?", (task_id,)
                ).fetchone()
                return [dict(row)] if row else []

            clauses: list[str] = []
            params: list[Any] = []
            if status is not None:
                clauses.append("status = ?")
                params.append(status)

            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(limit)
            rows = conn.execute(
                f"SELECT * FROM background_tasks{where} ORDER BY {order_clause} LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def _query_user_profile(self, filters: dict[str, Any]) -> list[dict]:
        category = filters.get("id")
        with self._db.get_db() as conn:
            if category:
                row = conn.execute(
                    "SELECT * FROM user_profile WHERE category = ?", (category,)
                ).fetchone()
                return [dict(row)] if row else []
            rows = conn.execute("SELECT * FROM user_profile ORDER BY category").fetchall()
        return [dict(r) for r in rows]
