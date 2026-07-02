"""Structured logging configuration for the backend."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog + stdlib logging for development-friendly structured output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _request_id_processor,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
    )


def _request_id_processor(
    _logger: object, _method_name: str, event_dict: "MutableMapping[str, Any]",
) -> "Mapping[str, Any]":
    """Attach the current request id (if any) to every structured log line."""
    try:
        from app.main import request_id_var
        rid = request_id_var.get()
        if rid:
            event_dict["request_id"] = rid
    except Exception:
        pass
    return event_dict
