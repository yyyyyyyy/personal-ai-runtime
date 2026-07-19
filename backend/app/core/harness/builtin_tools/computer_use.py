"""Computer Use MCP Server — screenshot, mouse click, keyboard input.

All operations go through the Runtime's governance layer (4-Gate CapabilityGateway).
Most actions (including screenshot) are needs_user; screen_size is auto_allow.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class ComputerUseServer:
    """Safe computer control with governance enforcement."""

    def __init__(self):
        self._screenshot_module: Any = None
        self._pyautogui: Any = None

    def _ensure_mss(self):
        if self._screenshot_module is None:
            try:
                import mss
                self._screenshot_module = mss
            except ImportError:
                raise RuntimeError(
                    "Computer Use requires 'mss' library. Install: pip install mss"
                )

    def _ensure_pyautogui(self):
        if self._pyautogui is None:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True  # Move to corner to abort
                self._pyautogui = pyautogui
            except ImportError:
                raise RuntimeError(
                    "Computer Use requires 'pyautogui' library. Install: pip install pyautogui"
                )

    @staticmethod
    def _set_clipboard(text: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(text)
            return
        except Exception:
            pass
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()

    def _paste_text(self) -> None:
        if sys.platform == "darwin":
            self._pyautogui.hotkey("command", "v")
        else:
            self._pyautogui.hotkey("ctrl", "v")

    def screenshot(self, region: str = "full") -> str:
        """Take a screenshot and return base64-encoded PNG."""
        try:
            self._ensure_mss()
            with self._screenshot_module.mss() as sct:
                if region == "primary":
                    monitor = sct.monitors[1]
                else:
                    monitor = sct.monitors[0]

                img = sct.grab(monitor)
                png_bytes = self._screenshot_module.tools.to_png(img.rgb, img.size)
                b64 = base64.b64encode(png_bytes).decode("utf-8")
                return json.dumps({
                    "status": "ok",
                    "image_base64": b64,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": len(png_bytes),
                    "hint": "Image is base64-encoded PNG. Use screen coordinates (x,y) for click/type operations.",
                })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def click(self, x: int, y: int, button: str = "left") -> str:
        """Click at screen coordinates."""
        try:
            self._ensure_pyautogui()
            self._pyautogui.click(x, y, button=button)
            return json.dumps({
                "status": "ok",
                "action": "click",
                "x": x, "y": y,
                "button": button,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def type_text(self, text: str, interval: float = 0.05) -> str:
        """Type text at the current cursor position.

        ASCII uses keystroke simulation; non-ASCII (e.g. CJK) uses clipboard
        paste because ``typewrite`` can't emit those characters.
        """
        if not text:
            return json.dumps({"status": "error", "error": "Empty text"})

        try:
            self._ensure_pyautogui()
            method = "typewrite"
            if any(ord(ch) > 127 for ch in text):
                self._set_clipboard(text)
                self._paste_text()
                method = "clipboard_paste"
            else:
                self._pyautogui.typewrite(text, interval=interval)
            return json.dumps({
                "status": "ok",
                "action": "type",
                "length": len(text),
                "method": method,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def move(self, x: int, y: int, duration: float = 0.3) -> str:
        """Move mouse to coordinates (no click)."""
        try:
            self._ensure_pyautogui()
            self._pyautogui.moveTo(x, y, duration=duration)
            return json.dumps({
                "status": "ok",
                "action": "move",
                "x": x, "y": y,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def scroll(self, clicks: int = 3) -> str:
        """Scroll the mouse wheel."""
        try:
            self._ensure_pyautogui()
            self._pyautogui.scroll(clicks)
            return json.dumps({
                "status": "ok",
                "action": "scroll",
                "clicks": clicks,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def press_key(self, key: str) -> str:
        """Press a keyboard key or combination."""
        try:
            self._ensure_pyautogui()
            self._pyautogui.hotkey(*key.split("+"))
            return json.dumps({
                "status": "ok",
                "action": "press_key",
                "key": key,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def screen_size(self) -> str:
        """Get the current screen resolution."""
        try:
            self._ensure_pyautogui()
            w, h = self._pyautogui.size()
            return json.dumps({
                "status": "ok",
                "width": w,
                "height": h,
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})


computer_use_server = ComputerUseServer()
