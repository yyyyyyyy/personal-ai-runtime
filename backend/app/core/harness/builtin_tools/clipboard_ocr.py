"""Clipboard & OCR MCP Server — read clipboard text and OCR image files."""

import json
import subprocess


class ClipboardOCRServer:
    """Clipboard operations and image-file text recognition (opt-in advanced)."""

    def get_clipboard_text(self) -> str:
        """Get current clipboard text content."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return json.dumps({"content": text[:5000], "length": len(text)})
        except Exception:
            try:
                result = subprocess.run(
                    ["powershell", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5,
                )
                return json.dumps({"content": result.stdout[:5000], "length": len(result.stdout)})
            except Exception:
                return json.dumps({"content": "", "note": "Clipboard read failed (GUI/X11 required)"})

    def ocr_file(self, path: str) -> str:
        """Perform OCR on an image file."""
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(path)
            text = pytesseract.image_to_string(img)
            return json.dumps({"file": path, "text": text[:3000], "length": len(text)})
        except ImportError as e:
            return json.dumps({"error": f"Dependency missing: {e}"})
        except Exception as e:
            return json.dumps({"error": str(e)})


clipboard_ocr_server = ClipboardOCRServer()
