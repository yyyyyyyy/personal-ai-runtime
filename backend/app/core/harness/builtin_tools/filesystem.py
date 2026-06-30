"""Filesystem MCP Server — safe file read/write/search within allowed directories."""

import json
from pathlib import Path

from app.config import BASE_DIR, settings


def _parse_path_list(raw: str, default: list[str]) -> list[str]:
    if not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def default_allowed_dirs() -> list[str]:
    return _parse_path_list(
        settings.filesystem_allowed_dirs,
        [str(BASE_DIR.resolve()), str(Path.home())],
    )


def default_protected_paths() -> list[str]:
    base = BASE_DIR.resolve()
    runtime = base / "backend/app/core/runtime"
    defaults = [
        str(runtime / "kernel"),
        str(base / "backend/scripts/check_boundary.py"),
        str(base / "backend/capability_policy.json"),
        str(runtime / "capability_policy.py"),
        str(runtime / "taint.py"),
        str(runtime / "sensitive_router.py"),
        str(base / ".env"),
        str(base / ".git"),
    ]
    extra = [item.strip() for item in settings.filesystem_protected_paths.split(",") if item.strip()]
    return defaults + extra


class FilesystemServer:
    """Filesystem operations with safety bounds and governance write protection."""

    def __init__(
        self,
        allowed_dirs: list[str] | None = None,
        protected_paths: list[str] | None = None,
    ):
        raw_allowed = allowed_dirs if allowed_dirs is not None else default_allowed_dirs()
        self.allowed_dirs = [
            str(Path(d).expanduser().resolve())
            for d in raw_allowed
        ]
        raw_protected = protected_paths if protected_paths is not None else default_protected_paths()
        self.protected_paths = [
            str(Path(p).expanduser().resolve())
            for p in raw_protected
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

    def _is_env_secret_file(self, p: Path) -> bool:
        """Block .env secrets in any directory; allow .env.example templates."""
        if p.name == ".env.example":
            return False
        if p.name == ".env":
            return True
        if p.name.startswith(".env."):
            return True
        return False

    def _is_protected(self, path: str) -> bool:
        """Check if a path is governance-protected (agent must not write here)."""
        try:
            p = Path(path).expanduser().resolve()
            if self._is_env_secret_file(p):
                return True
            for protected in self.protected_paths:
                prot = Path(protected).expanduser().resolve()
                if p == prot:
                    return True
                if prot.is_dir() and p.is_relative_to(prot):
                    return True
            return False
        except Exception:
            return True

    def _write_denied(self, path: str) -> str | None:
        if not self._is_safe(path):
            return json.dumps({"error": "Access denied: path outside allowed directories"})
        if self._is_protected(path):
            return json.dumps({
                "error": (
                    "Access denied: path is protected "
                    "(kernel/governance files cannot be modified by agent)"
                ),
                "path": path,
            })
        return None

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
        denied = self._write_denied(path)
        if denied:
            return denied

        p = Path(path).expanduser().resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return json.dumps({"success": True, "path": str(p), "size": p.stat().st_size})
        except PermissionError:
            return json.dumps({"error": "Permission denied"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    def apply_patch(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """Apply a search-replace patch to a text file."""
        denied = self._write_denied(path)
        if denied:
            return denied

        p = Path(path).expanduser().resolve()
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        if p.is_dir():
            return json.dumps({"error": f"Path is a directory: {path}"})
        if not old_string:
            return json.dumps({"error": "old_string must not be empty"})

        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return json.dumps({"error": "Cannot patch binary file as text"})
        except PermissionError:
            return json.dumps({"error": "Permission denied"})

        count = content.count(old_string)
        if count == 0:
            return json.dumps({"error": "old_string not found in file", "path": str(p)})
        if count > 1 and not replace_all:
            return json.dumps({
                "error": (
                    f"old_string appears {count} times; "
                    "set replace_all=true or use a more specific old_string"
                ),
                "occurrences": count,
            })

        replacements = count if replace_all else 1
        new_content = content.replace(old_string, new_string, replacements if replace_all else 1)

        try:
            p.write_text(new_content, encoding="utf-8")
            return json.dumps({
                "success": True,
                "path": str(p),
                "replacements": replacements,
                "size": p.stat().st_size,
            })
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

        results: list[dict[str, str]] = []
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
