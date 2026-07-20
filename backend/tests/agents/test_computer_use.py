"""Unit tests for Computer Use MCP server (import-safe, no hardware required)."""
from __future__ import annotations

import json

import pytest

from app.core.harness.builtin_tools.computer_use import ComputerUseServer


class TestComputerUseServer:
    def test_init(self):
        s = ComputerUseServer()
        assert s._screenshot_module is None
        assert s._pyautogui is None

    def test_screenshot_without_mss(self):
        s = ComputerUseServer()
        result = json.loads(s.screenshot())
        assert result["status"] == "error"
        assert "mss" in result["error"].lower()

    def test_click_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.click(100, 100))
        assert result["status"] == "error"
        assert "pyautogui" in result["error"].lower()

    def test_type_empty_text(self):
        s = ComputerUseServer()

        class FakePyautogui:
            FAILSAFE = True

            @staticmethod
            def typewrite(text, interval=0.05):
                return None

            @staticmethod
            def hotkey(*_args):
                return None

        try:
            s._pyautogui = FakePyautogui()
            result = json.loads(s.type_text(""))
            assert result["status"] == "error"
            assert "empty" in result["error"].lower()
        finally:
            s._pyautogui = None

    def test_type_cjk_uses_clipboard_paste(self, monkeypatch):
        s = ComputerUseServer()
        pasted: list[str] = []

        class FakePyautogui:
            FAILSAFE = True

            @staticmethod
            def typewrite(text, interval=0.05):
                raise AssertionError("typewrite must not be used for CJK")

            @staticmethod
            def hotkey(*args):
                pasted.append("+".join(args))

        monkeypatch.setattr(s, "_set_clipboard", lambda text: None)
        try:
            s._pyautogui = FakePyautogui()
            result = json.loads(s.type_text("你好"))
            assert result["status"] == "ok"
            assert result["method"] == "clipboard_paste"
            assert pasted
        finally:
            s._pyautogui = None

    def test_server_singleton(self):
        from app.core.harness.builtin_tools.computer_use import computer_use_server

        assert isinstance(computer_use_server, ComputerUseServer)

    def test_screenshot_full_vs_primary(self):
        s = ComputerUseServer()
        r1 = json.loads(s.screenshot("full"))
        r2 = json.loads(s.screenshot("primary"))
        assert r1["status"] == r2["status"]


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    [
        ("type_text", ("hello",), {}),
        ("move", (100, 100), {}),
        ("scroll", (3,), {}),
        ("press_key", ("enter",), {}),
        ("screen_size", (), {}),
        ("screenshot", ("unknown",), {}),
        ("click", (0, 0), {"button": "right"}),
        ("click", (0, 0), {"button": "middle"}),
        ("move", (50, 50), {"duration": 1.0}),
        ("scroll", (-3,), {}),
        ("press_key", ("ctrl+v",), {}),
        ("type_text", ("x",), {"interval": 0.1}),
    ],
)
def test_methods_error_without_deps(method, args, kwargs):
    """Missing pyautogui/mss must fail closed for all input variants."""
    s = ComputerUseServer()
    result = json.loads(getattr(s, method)(*args, **kwargs))
    assert result["status"] == "error"
