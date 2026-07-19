"""Unit tests for Computer Use MCP server (import-safe, no hardware required)."""
import json

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

    def test_type_text_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.type_text("hello"))
        assert result["status"] == "error"

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

    def test_move_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.move(100, 100))
        assert result["status"] == "error"

    def test_scroll_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.scroll(3))
        assert result["status"] == "error"

    def test_press_key_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.press_key("enter"))
        assert result["status"] == "error"

    def test_screen_size_without_pyautogui(self):
        s = ComputerUseServer()
        result = json.loads(s.screen_size())
        assert result["status"] == "error"

    def test_server_singleton(self):
        from app.core.harness.builtin_tools.computer_use import computer_use_server
        assert isinstance(computer_use_server, ComputerUseServer)

    def test_screenshot_full_vs_primary(self):
        s = ComputerUseServer()
        r1 = json.loads(s.screenshot("full"))
        r2 = json.loads(s.screenshot("primary"))
        assert r1["status"] == r2["status"]  # both fail the same way


class TestComputerUseServerEdgeCases:
    def test_screenshot_region_unknown_is_full(self):
        s = ComputerUseServer()
        r = json.loads(s.screenshot("unknown"))
        assert r["status"] == "error"

    def test_click_right_button(self):
        s = ComputerUseServer()
        r = json.loads(s.click(0, 0, button="right"))
        assert r["status"] == "error"

    def test_click_middle_button(self):
        s = ComputerUseServer()
        r = json.loads(s.click(0, 0, button="middle"))
        assert r["status"] == "error"

    def test_move_with_duration(self):
        s = ComputerUseServer()
        r = json.loads(s.move(50, 50, duration=1.0))
        assert r["status"] == "error"

    def test_scroll_up_and_down(self):
        s = ComputerUseServer()
        r1 = json.loads(s.scroll(5))
        r2 = json.loads(s.scroll(-3))
        assert r1["status"] == "error"
        assert r2["status"] == "error"

    def test_press_key_combo(self):
        s = ComputerUseServer()
        r = json.loads(s.press_key("ctrl+v"))
        assert r["status"] == "error"

    def test_type_with_interval(self):
        s = ComputerUseServer()
        r = json.loads(s.type_text("x", interval=0.1))
        assert r["status"] == "error"
