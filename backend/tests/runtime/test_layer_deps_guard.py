"""Tests for scripts/check_layer_deps.py responsibility-edge guard."""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def run_check(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.check_layer_deps", *args],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )


def _write_tree(fake_app: Path) -> None:
    for part in ("product", "api", "store", "core/runtime"):
        (fake_app / part).mkdir(parents=True, exist_ok=True)


class TestLayerDepsGuard:
    def test_codebase_passes_with_allowlisted_debt(self):
        result = run_check()
        assert result.returncode == 0, result.stderr or result.stdout
        assert "LAYER DEPS OK" in result.stdout

    def test_inventory_lists_known_debt(self):
        result = run_check("--inventory")
        assert result.returncode == 0, result.stderr or result.stdout
        assert "LAYER DEPS INVENTORY" in result.stdout
        assert "New (would fail CI): 0" in result.stdout
        assert "runtime_to_product" in result.stdout
        assert "store_to_runtime" in result.stdout

    def test_strict_mode_fails_while_debt_remains(self):
        result = run_check("--strict")
        assert result.returncode == 1
        assert "STRICT FAIL" in (result.stderr or result.stdout)

    def test_new_runtime_to_product_not_in_allowlist_fails(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(BACKEND))
        try:
            import scripts.check_layer_deps as mod

            fake_app = tmp_path / "app"
            _write_tree(fake_app)
            (fake_app / "core" / "runtime" / "sneaky.py").write_text(
                "from app.product.inbox import apply_inbox_poll_payload\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(mod, "APP_ROOT", fake_app)

            _known, new = mod.partition(mod.scan())
            assert any(v[2] == "runtime_to_product" for v in new)
        finally:
            sys.path.pop(0)

    def test_store_to_runtime_detected(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(BACKEND))
        try:
            import scripts.check_layer_deps as mod

            fake_app = tmp_path / "app"
            _write_tree(fake_app)
            (fake_app / "store" / "db.py").write_text(
                "from app.core.runtime.runtime_container import runtime\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(mod, "APP_ROOT", fake_app)
            _known, new = mod.partition(mod.scan())
            assert any(v[2] == "store_to_runtime" for v in new)
        finally:
            sys.path.pop(0)

    def test_api_private_import_detected(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(BACKEND))
        try:
            import scripts.check_layer_deps as mod

            fake_app = tmp_path / "app"
            _write_tree(fake_app)
            (fake_app / "api" / "x.py").write_text(
                "from app.core.runtime.runtime_config import _is_masked\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(mod, "APP_ROOT", fake_app)
            _known, new = mod.partition(mod.scan())
            assert any(v[2] == "api_private_import" for v in new)
        finally:
            sys.path.pop(0)

    def test_product_kernel_type_and_constants_are_abi(self, tmp_path, monkeypatch):
        sys.path.insert(0, str(BACKEND))
        try:
            import scripts.check_layer_deps as mod

            fake_app = tmp_path / "app"
            _write_tree(fake_app)
            (fake_app / "product" / "ok.py").write_text(
                "from app.core.runtime.kernel import Kernel\n"
                "from app.core.runtime.kernel import constants\n"
                "from app.core.runtime.kernel.constants import EVENT_X\n"
                "from app.core.runtime import read_ports\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(mod, "APP_ROOT", fake_app)
            violations = mod.scan()
            assert violations == [], violations
        finally:
            sys.path.pop(0)

    def test_product_kernel_submodule_is_debt(self, tmp_path, monkeypatch):
        """sovereignty_ops under kernel must not ride the Kernel-type ABI."""
        sys.path.insert(0, str(BACKEND))
        try:
            import scripts.check_layer_deps as mod

            fake_app = tmp_path / "app"
            _write_tree(fake_app)
            (fake_app / "product" / "bad.py").write_text(
                "from app.core.runtime.kernel.sovereignty_ops import rebuild_all\n",
                encoding="utf-8",
            )
            monkeypatch.setattr(mod, "APP_ROOT", fake_app)
            _known, new = mod.partition(mod.scan())
            assert any(
                v[2] == "product_deep_runtime"
                and "sovereignty_ops" in v[3]
                for v in new
            ), new
        finally:
            sys.path.pop(0)
