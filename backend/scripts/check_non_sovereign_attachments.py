"""CI gate: non-sovereignty attachments stay explicitly registered (Path B).

Knowledge (and future peers) must not silently become a second Truth Layer.
This check enforces the registration in ``table_registry.NON_SOVEREIGN_ATTACHMENTS``
and that each attachment stays outside governed / memory-index event machinery.

Usage:
    python -m scripts.check_non_sovereign_attachments
"""

from __future__ import annotations

import importlib
import sys

from scripts._bootstrap import prepare_script_env

prepare_script_env()

_REQUIRED_META_KEYS = frozenset({
    "kind",
    "owner_module",
    "sqlite",
    "vector_collection",
    "write_path",
    "notes",
})

# Attachment ids that must always be present (Path B baseline).
_REQUIRED_ATTACHMENT_IDS = frozenset({"knowledge"})


def check(*, verbose: bool = True) -> int:
    from app.core.runtime.kernel.constants import MEMORY_INDEX_EVENT_TYPES
    from app.store.table_registry import (
        GOVERNED_TABLES,
        NON_SOVEREIGN_ATTACHMENTS,
    )

    violations = 0

    missing_ids = sorted(_REQUIRED_ATTACHMENT_IDS - set(NON_SOVEREIGN_ATTACHMENTS))
    if missing_ids:
        violations += 1
        if verbose:
            print(
                f"  [FAIL] required attachments missing from registry: {missing_ids}"
            )

    for attachment_id, meta in sorted(NON_SOVEREIGN_ATTACHMENTS.items()):
        missing_keys = sorted(_REQUIRED_META_KEYS - set(meta))
        if missing_keys:
            violations += 1
            if verbose:
                print(
                    f"  [FAIL] {attachment_id}: missing keys {missing_keys}"
                )

        owner = meta.get("owner_module", "")
        if owner:
            try:
                importlib.import_module(owner)
            except ImportError as exc:
                violations += 1
                if verbose:
                    print(
                        f"  [FAIL] {attachment_id}: owner_module import failed: {exc}"
                    )

        # Attachment id and common aliases must not be governed tables.
        for name in (attachment_id, f"{attachment_id}_docs", f"{attachment_id}_chunks"):
            if name in GOVERNED_TABLES:
                violations += 1
                if verbose:
                    print(
                        f"  [FAIL] {name!r} is in GOVERNED_TABLES "
                        f"(attachment {attachment_id!r} must stay non-sovereign)"
                    )

        vector = meta.get("vector_collection", "")
        if vector and vector in GOVERNED_TABLES:
            violations += 1
            if verbose:
                print(
                    f"  [FAIL] vector_collection {vector!r} collides with "
                    f"GOVERNED_TABLES (attachment {attachment_id!r})"
                )

        # Memory index sync must not claim this attachment's document events.
        needle = attachment_id.lower()
        claimed = {
            t for t in MEMORY_INDEX_EVENT_TYPES
            if needle in t.lower()
        }
        if claimed:
            violations += 1
            if verbose:
                print(
                    f"  [FAIL] MEMORY_INDEX_EVENT_TYPES claims {attachment_id} "
                    f"types: {sorted(claimed)}"
                )

    # Knowledge-specific vector collection name (stable contract with VectorStore).
    knowledge_meta = NON_SOVEREIGN_ATTACHMENTS.get("knowledge") or {}
    if knowledge_meta.get("vector_collection") not in (None, "knowledge"):
        violations += 1
        if verbose:
            print(
                "  [FAIL] knowledge.vector_collection must be 'knowledge' "
                f"(got {knowledge_meta.get('vector_collection')!r})"
            )

    if verbose and violations == 0:
        print(
            f"NON-SOVEREIGN ATTACHMENTS OK — "
            f"{len(NON_SOVEREIGN_ATTACHMENTS)} registered "
            f"({', '.join(sorted(NON_SOVEREIGN_ATTACHMENTS))})"
        )
    return 1 if violations else 0


def main() -> int:
    return check(verbose=True)


if __name__ == "__main__":
    sys.exit(main())
