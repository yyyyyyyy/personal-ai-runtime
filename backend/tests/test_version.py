"""Tests for version module."""

from app.version import APP_NAME, VERSION


def test_app_name():
    assert APP_NAME == "Personal AI Runtime"


def test_version_is_set():
    assert VERSION is not None
    assert len(VERSION) > 0
    assert VERSION.count(".") >= 1  # semver: major.minor.patch
