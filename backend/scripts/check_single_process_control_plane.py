#!/usr/bin/env python
"""Guard: control plane stays single-process (INV-W6 / Non-goal multi-worker).

Fails if new code under app/ introduces a second Scheduler/RuntimeLoop process
entrypoint (multiprocessing Process targeting those classes, or a dedicated
worker __main__ that starts them outside FastAPI lifespan).

This is a *prevention* guard for Non-goal scope — not a distributed lease impl.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts._bootstrap import prepare_script_env

prepare_script_env()

BACKEND = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND / "app"

_FORBIDDEN_TARGETS = frozenset({
    "Scheduler",
    "RuntimeLoop",
    "ensure_scheduler",
    "agent_scheduler",
})


def _scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: syntax error: {exc}"]
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name not in {"Process", "Popen"}:
            continue
        # multiprocessing.Process(..., target=Scheduler) style
        for kw in node.keywords:
            if kw.arg != "target":
                continue
            tgt = kw.value
            tgt_name = ""
            if isinstance(tgt, ast.Name):
                tgt_name = tgt.id
            elif isinstance(tgt, ast.Attribute):
                tgt_name = tgt.attr
            if tgt_name in _FORBIDDEN_TARGETS:
                rel = path.relative_to(APP_ROOT).as_posix()
                hits.append(
                    f"{rel}:{node.lineno}: Process(target={tgt_name}) "
                    "violates single-process control plane (INV-W6)"
                )
    # Soft scan: dedicated worker module named like scheduler_worker.py
    if path.name in {
        "scheduler_worker.py",
        "runtime_worker.py",
        "lane_a_worker.py",
    }:
        rel = path.relative_to(APP_ROOT).as_posix()
        hits.append(
            f"{rel}:1: forbidden control-plane worker module name (INV-W6)"
        )
    return hits


def main() -> int:
    violations: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        violations.extend(_scan_file(path))
    if violations:
        print("SINGLE-PROCESS CONTROL PLANE FAILED", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nDistributed lease / multi-worker Scheduler is a Non-goal. "
            "See docs/02-concepts/execution-model.md",
            file=sys.stderr,
        )
        return 1
    print("SINGLE-PROCESS CONTROL PLANE OK (INV-W6)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
