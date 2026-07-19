"""Request-scoped context shared by middleware, logging, and handlers.

Kept outside ``app.main`` so logging processors can import it without a
circular dependency on the FastAPI application module.
"""

from __future__ import annotations

from contextvars import ContextVar

# Populated by RequestIDMiddleware on every HTTP request so structured logs
# can correlate all log lines within a single request.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request id (empty string outside a request)."""
    return request_id_var.get()
