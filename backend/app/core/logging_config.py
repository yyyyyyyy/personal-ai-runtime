"""Structured logging configuration for the backend.

Routes both structlog and stdlib ``logging`` through the same
``ProcessorFormatter`` pipeline so request_id / timestamps stay consistent.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

from app.core.request_context import request_id_var

# Marker so reconfigure only removes handlers we installed.
_OWNED_HANDLER_ATTR = "_par_structlog_handler"


def configure_logging(
    level: int = logging.INFO,
    *,
    json_logs: bool | None = None,
) -> None:
    """Configure structlog + stdlib logging with a shared processor chain.

    ``json_logs`` defaults from ``LOG_JSON=1|true|yes`` when omitted.
    Only replaces handlers previously installed by this function.
    """
    if json_logs is None:
        json_logs = os.environ.get("LOG_JSON", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _request_id_processor,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    setattr(handler, _OWNED_HANDLER_ATTR, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _OWNED_HANDLER_ATTR, False):
            root.removeHandler(existing)
            existing.close()
    root.addHandler(handler)
    root.setLevel(level)


def _request_id_processor(
    _logger: object,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> Mapping[str, Any]:
    """Attach the current request id (if any) to every structured log line."""
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict
