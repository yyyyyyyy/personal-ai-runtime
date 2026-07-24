# ADR-R015: Policy register idempotent across MCP restart

- **Status**: Accepted
- **Date**: 2026-07-24
- **Context**: MCP mesh `stop()` called `clear_external_tools()` which emitted `PolicyUpdated(revoked)` for every external tool; the next `start()` re-emitted `PolicyCreated`. On the personal DB this cycle produced ~74% of `event_log` rows (745 Created + 677 revoked Updates) with zero risk-tier changes.
- **Decision**: `clear_external_tools()` defaults to **in-memory only** (process lifecycle). Durable revoke requires `persist=True` or `revoke_external_tools(names)`. Register/seed share `_upsert_policy` (INV-C6): same capability + same active risk → no emit; revoked → `PolicyUpdated(status=active)`. Historical pollution is cleaned via `python -m scripts.compact_policy_events --apply`.
- **Consequences**: Mesh restart no longer floods the log. Intentional tool removal must call revoke explicitly. Compaction rewrites `event_log` seqs (backup required). See INV-C6.
