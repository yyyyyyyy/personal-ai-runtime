#!/usr/bin/env python
"""Quick CLI to log friction during dogfood self-use.

Examples:
  python scripts/friction.py "收件箱摘要太长，看不清重点"
  python scripts/friction.py "审批弹窗文案看不懂" --area tools --severity high
  python scripts/friction.py --list
  python scripts/friction.py --list --status open
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")

from app.product.friction_log import (  # noqa: E402
    VALID_AREAS,
    VALID_SEVERITIES,
    list_friction,
    log_friction,
    resolve_friction,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Log dogfood friction points")
    parser.add_argument("note", nargs="?", help="What felt bad")
    parser.add_argument(
        "--area",
        default="other",
        choices=sorted(VALID_AREAS),
        help="Product area",
    )
    parser.add_argument(
        "--severity",
        default="medium",
        choices=sorted(VALID_SEVERITIES),
        help="How painful",
    )
    parser.add_argument("--list", action="store_true", help="List friction points")
    parser.add_argument("--status", choices=("open", "resolved"), help="Filter by status")
    parser.add_argument("--resolve", metavar="ID", help="Mark friction as resolved")
    args = parser.parse_args()

    if args.list:
        items = list_friction(status=args.status)
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if args.resolve:
        entry = resolve_friction(args.resolve)
        if entry is None:
            print(f"Not found: {args.resolve}", file=sys.stderr)
            return 1
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0

    if not args.note:
        parser.error("note is required unless --list or --resolve is used")

    entry = log_friction(args.note, area=args.area, severity=args.severity)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
