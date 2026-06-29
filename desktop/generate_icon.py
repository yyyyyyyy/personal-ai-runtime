#!/usr/bin/env python3
"""Generate tray icon for Electron desktop app (stdlib only, no Pillow needed)."""
import struct
import zlib
from pathlib import Path


def make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    chunk = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    return struct.pack(">I", len(data)) + chunk + crc


def create_png(width: int, height: int) -> bytes:
    """Create a 32x32 PNG with a rounded blue circle on transparent background."""
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR: RGBA, 8-bit
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # RGBA pixel data
    cx = width / 2 - 0.5
    cy = height / 2 - 0.5
    r = min(width, height) / 2 - 2

    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter: none
        for x in range(width):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= r * r:
                raw += bytes([59, 130, 246, 255])  # blue #3B82F6
            else:
                raw += bytes([0, 0, 0, 0])  # transparent
    compressed = zlib.compress(raw)
    idat = make_chunk(b"IDAT", compressed)

    iend = make_chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def main():
    icon_path = Path(__file__).parent / "icon.png"
    png = create_png(32, 32)
    icon_path.write_bytes(png)
    print(f"Icon saved to {icon_path}")


if __name__ == "__main__":
    main()
