"""Dynamic import guard — allowlist + intentional violation detection."""

from __future__ import annotations

from scripts.check_dynamic_imports import IMPORTLIB_ALLOWLIST, main


def test_dynamic_import_allowlist_covers_bound_proxy_only():
    assert ("store/bound_proxy.py", 39) in IMPORTLIB_ALLOWLIST
    assert len(IMPORTLIB_ALLOWLIST) == 1


def test_dynamic_import_guard_passes_on_tree():
    assert main() == 0


def test_guard_would_flag_unallowlisted_importlib(tmp_path, monkeypatch):
    """Fixture: a fake app file with importlib must fail the scanner."""
    import scripts.check_dynamic_imports as mod

    fake_app = tmp_path / "app"
    fake_app.mkdir()
    bad = fake_app / "evil.py"
    bad.write_text(
        "import importlib\nimportlib.import_module('os')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "APP_ROOT", fake_app)
    monkeypatch.setattr(mod, "IMPORTLIB_ALLOWLIST", frozenset())
    assert mod.main() == 1


def test_guard_would_flag_unallowlisted_dunder_import(tmp_path, monkeypatch):
    import scripts.check_dynamic_imports as mod

    fake_app = tmp_path / "app"
    fake_app.mkdir()
    bad = fake_app / "evil2.py"
    bad.write_text("__import__('os')\n", encoding="utf-8")
    monkeypatch.setattr(mod, "APP_ROOT", fake_app)
    monkeypatch.setattr(mod, "IMPORTLIB_ALLOWLIST", frozenset())
    assert mod.main() == 1
