"""Computer Use MCP Server — screenshot, mouse click, keyboard input.

All operations go through the Runtime's governance layer (4-Gate CapabilityGateway).
Screenshot is auto_allow; click/type are needs_user (high risk).
"""

from __future__ import annotations

import base64
import json
import logging
import tempfile
from pathlib import Path
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

    def screenshot(self, region: str = "full") -> str:
        """Take a screenshot and return base64-encoded PNG.

        Args:
            region: "full" for entire screen, or "primary" for primary monitor only.
        """
        try:
            self._ensure_mss()
            with self._screenshot_module.mss() as sct:
                if region == "primary":
                    monitor = sct.monitors[1]
                else:
                    monitor = sct.monitors[0]

                img = sct.grab(monitor)

                # Save to temp file and read as base64
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    self._screenshot_module.tools.to_png(img.rgb, img.size, output=tmp.name)
                    tmp_path = Path(tmp.name)

                data = tmp_path.read_bytes()
                tmp_path.unlink()

                b64 = base64.b64encode(data).decode("utf-8")
                return json.dumps({
                    "status": "ok",
                    "image_base64": b64,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": len(data),
                    "hint": "Image is base64-encoded PNG. Use screen coordinates (x,y) for click/type operations.",
                })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def click(self, x: int, y: int, button: str = "left") -> str:
        """Click at screen coordinates.

        Args:
            x: X coordinate (pixels from left).
            y: Y coordinate (pixels from top).
            button: "left", "right", or "middle".
        """
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

        Args:
            text: The text to type.
            interval: Seconds between keystrokes (slower = safer with complex UIs).
        """
        if not text:
            return json.dumps({"status": "error", "error": "Empty text"})

        try:
            self._ensure_pyautogui()
            self._pyautogui.typewrite(text, interval=interval)
            return json.dumps({
                "status": "ok",
                "action": "type",
                "length": len(text),
            })
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)})

    def move(self, x: int, y: int, duration: float = 0.3) -> str:
        """Move mouse to coordinates (no click).

        Args:
            x: X coordinate.
            y: Y coordinate.
            duration: Movement animation duration in seconds.
        """
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
        """Scroll the mouse wheel.

        Args:
            clicks: Positive = scroll up, negative = scroll down.
        """
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
        """Press a keyboard key or combination.

        Args:
            key: Key name (e.g. "enter", "escape", "ctrl+c", "alt+tab").
        """
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
