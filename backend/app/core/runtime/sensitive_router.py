"""Sensitive operation routing — local Ollama classification when enabled."""

from __future__ import annotations

import re

from app.config import settings

SENSITIVE_PATTERNS = [
    re.compile(r"\b(password|api[_-]?key|secret|token)\b", re.I),
    re.compile(r"\.(pem|key|env)$", re.I),
    re.compile(r"/Users/|/home/|~/|C:\\Users\\|C:/Users/", re.I),
]


class SensitiveRouter:
  def is_sensitive_capability(self, name: str, args: dict | None = None) -> bool:
      if not settings.sensitive_ops_local:
          return False
      write_tools = {"apply_patch", "write_file", "shell_exec", "send_email"}
      if name in write_tools:
          return True
      if args:
          blob = str(args)
          return any(p.search(blob) for p in SENSITIVE_PATTERNS)
      return False

  def elevated_risk(self, name: str, args: dict | None = None) -> str:
      """Return 'high' if sensitive, else defer to policy."""
      if self.is_sensitive_capability(name, args):
          return "high"
      return ""


sensitive_router = SensitiveRouter()
