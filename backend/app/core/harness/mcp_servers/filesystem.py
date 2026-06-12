"""Filesystem MCP Server — safe file read/write/search within allowed directories."""

import json
from pathlib import Path


class FilesystemServer:
    """Filesystem operations with safety bounds."""

    def __init__(self, allowed_dirs: list[str] | None = None):
        self.allowed_dirs = [
            str(Path(d).expanduser().resolve())
            for d in (allowed_dirs or ["~/"])
        ]

    def _is_safe(self, path: str) -> bool:
        """Check if a path is within allowed directories."""
        try:
            p = Path(path).expanduser().resolve()
            for allowed in self.allowed_dirs:
                base = Path(allowed).resolve()
                if p == base or p.is_relative_to(base):
                    return True
            return False
        except Exception:
            return False

    def read_file(self, path: str, max_lines: int = 500) -> str:
        """Read a text file with safety check."""
        if not self._is_safe(path):
            return json.dumps({"error": "Access denied: path outside allowed directories"})

        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        if p.is_dir():
            return json.dumps({"error": f"Path is a directory: {path}"})

        try:
            content = p.read_text(encoding="utf-8")
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines])
                content += f"\n... [showing {max_lines}/{len(lines)} lines]"
            if len(content) > 10000:
                content = content[:10000] + "\n... [content truncated]"
            return content
        except UnicodeDecodeError:
            return json.dumps({"error": "Cannot read binary file as text"})
        except PermissionError:
            return json.dumps({"error": "Permission denied"})

    def write_file(self, path: str, content: str) -> str:
        """Write a text file with safety check."""
        if not self._is_safe(path):
            return json.dumps({"error": "Access denied: path outside allowed directories"})

        p = Path(path).expanduser().resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return json.dumps({"success": True, "path": str(p), "size": p.stat().st_size})
        except PermissionError:
            return json.dumps({"error": "Permission denied"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def list_directory(self, path: str, pattern: str | None = None) -> str:
        """List directory contents with optional glob pattern."""
        if not self._is_safe(path):
            return json.dumps({"error": "Access denied: path outside allowed directories"})

        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"Directory not found: {path}"})
        if not p.is_dir():
            return json.dumps({"error": f"Not a directory: {path}"})

        try:
            if pattern:
                items_iter = p.glob(pattern)
            else:
                items_iter = p.iterdir()

            items = []
            for item in sorted(items_iter):
                try:
                    stat = item.stat()
                    items.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size": stat.st_size if item.is_file() else None,
                        "modified": stat.st_mtime,
                    })
                except Exception:
                    items.append({"name": item.name, "type": "unknown"})

            if len(items) > 200:
                items = items[:200]
                items.append({"name": "... (more items truncated)", "type": "info"})

            return json.dumps({"path": str(p), "count": len(items), "items": items}, indent=2)
        except PermissionError:
            return json.dumps({"error": "Permission denied"})

    def search_files(self, path: str, query: str) -> str:
        """Search for files matching a name query."""
        if not self._is_safe(path):
            return json.dumps({"error": "Access denied: path outside allowed directories"})

        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            return json.dumps({"error": f"Not a directory: {path}"})

        results = []
        try:
            for item in p.rglob(f"*{query}*"):
                if len(results) >= 50:
                    break
                results.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "dir" if item.is_dir() else "file",
                })
        except PermissionError:
            pass

        return json.dumps({"query": query, "count": len(results), "results": results}, indent=2)


filesystem_server = FilesystemServer()
