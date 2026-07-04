"""Tests for logging configuration."""

from app.core.logging_config import configure_logging


def test_configure_logging_smoke():
    configure_logging()
    import structlog

    log = structlog.get_logger("test")
    log.info("structured log smoke test", component="logging_config")

    # Verify structlog is usable — must not raise
    logger = structlog.get_logger(__name__)
    assert logger is not None
