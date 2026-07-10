"""Launch the FastAPI backend for the desktop app.

Embeddable CPython on Windows does not put the backend working directory on
sys.path, so `uvicorn app.main:app` fails with ModuleNotFoundError unless we
insert BACKEND_DIR first.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    backend_dir = os.environ.get("BACKEND_DIR", "").strip()
    if not backend_dir:
        print("BACKEND_DIR is not set", file=sys.stderr)
        sys.exit(1)

    backend_dir = os.path.abspath(backend_dir)
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    port = int(os.environ.get("BACKEND_PORT", "8000"))

    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
