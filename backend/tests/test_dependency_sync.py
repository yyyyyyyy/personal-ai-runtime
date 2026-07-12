"""Tests for the pre-install dependency/lock synchronization guard."""

from scripts import check_dependency_sync as sync


def test_removed_dependency_makes_stamped_lock_stale(tmp_path, monkeypatch, capsys):
    requirements = tmp_path / "requirements.txt"
    dev_requirements = tmp_path / "requirements-dev.txt"
    pyproject = tmp_path / "pyproject.toml"
    lock = tmp_path / "requirements.lock"

    requirements.write_text("example-package==1.0\n", encoding="utf-8")
    dev_requirements.write_text(
        "-r requirements.txt\npytest==9.1.1\n",
        encoding="utf-8",
    )
    pyproject.write_text(
        '[project]\ndependencies = ["example-package==1.0"]\n',
        encoding="utf-8",
    )
    lock.write_text(
        "example-package==1.0 \\\n"
        "    --hash=sha256:abc\n"
        "pytest==9.1.1 \\\n"
        "    --hash=sha256:def\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(sync, "REQUIREMENTS_PATH", requirements)
    monkeypatch.setattr(sync, "DEV_REQUIREMENTS_PATH", dev_requirements)
    monkeypatch.setattr(sync, "PYPROJECT_PATH", pyproject)
    monkeypatch.setattr(sync, "LOCK_PATH", lock)

    sync._stamp_lock_input_hashes()
    assert sync.main([]) == 0

    # Removing a direct dependency from both authoritative inputs used to pass:
    # the stale package was still present in the old lock. The input fingerprint
    # must now reject that lock.
    requirements.write_text("", encoding="utf-8")
    pyproject.write_text("[project]\ndependencies = []\n", encoding="utf-8")

    assert sync.main([]) == 1
    assert "requirements.lock is stale for requirements.txt" in capsys.readouterr().err
