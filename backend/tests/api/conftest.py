"""Conftest for tests/api.

HTTP ``client`` lives in ``tests/conftest.py`` (shared with integration).
SSE e2e still drives ``send_message`` directly; conversation setup uses ``client``.
"""
