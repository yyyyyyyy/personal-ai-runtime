# Changelog

All notable changes to Personal AI Runtime are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Version numbers match [`backend/app/version.py`](backend/app/version.py).

## [Unreleased]

### Security

- Knowledge upload rejects oversized files at the API boundary (413) before ingest
- Destructive system routes use request-body confirm codes (not query params); when `AUTH_TOKEN` is configured, Bearer auth is also required
- MCP external servers pin package versions and receive a minimal env (no parent secret inheritance)
- Rate limits use path-boundary matching, per-IP buckets, shared restore/export quotas, and LRU eviction
- Shell tool blocks background `&` / shell metacharacters; `*` globs remain allowed for coding agents (`shell=False`)
- Browser search URL-encodes query/site; fetch streams responses with a hard byte cap

### Changed

- Split `read_ports.py` into a domain-scoped `read_ports/` package (backward-compatible re-exports)
- Raise `runtime_files` architecture baseline 44→57 for the read_ports package split (same Read Port concept; one-year target remains ≤44)
- Knowledge API no longer imports `app.store` directly; document CRUD/search lives in `product/knowledge.py`
- Boundary guard: fail if `app/api/` imports `app.store`
- `VectorStore` reads `settings.vector_dir` at construction time so `reset_settings()` in tests takes effect
- Optional `TRUST_PROXY_HEADERS` for rate-limit keying behind a trusted reverse proxy

### Fixed

- Remove root-level debug dump `full_chat.txt` from the working tree
- Memory graph edge unit test import path after `read_ports` split
- Local-first destroy/import works again when `AUTH_TOKEN` is unset (confirm code only)

## [0.2.0]

### Added

- Event-sourced Kernel with governed projection tables and rebuild verification
- Streaming chat with tool loops, approval flow, and SSE delivery
- Memory extraction, semantic search (ChromaDB), portrait, and claim workflow
- Goals unified under `work_items`; inbox (Gmail), knowledge base RAG
- 3-gate capability governance, taint tracking, LLM egress audit
- Data sovereignty: export/import (plain + encrypted), destroy, snapshot/restore
- MCP harness: 26+ builtin tools + external MCP registry
- React frontend (Chat, Goals, Memories, Inbox, TrustReport, Dashboard, Settings, …)
- Electron desktop shell with tray and global shortcuts
- CI invariant matrix: boundary, rebuild, vector consistency, concept growth guards

### Changed

- Documentation consolidated under `docs/` with reading paths and subsystem guides

### Fixed

- Startup failures (governance seed, ContextPipeline, RuntimeLoop) now log at ERROR and appear in `/api/system/health` instead of being swallowed as DEBUG
- Removed dead `event_recorder` / `activity_log` wrapper and deprecated `prepare_llm_egress` aliases
- Docs aligned to 3-gate governance and CI coverage thresholds (runtime ≥75%)
- Taint write-class / external-ingestion sets loaded from `capability_policy.json` (single source)
- Notifications store `related_id` in the projection column instead of content prefix hack
- Frontend: empty-body `request()` handling, SSE `AbortSignal`, Goals/Inbox/Memories on TanStack Query
- Approvals/Knowledge/Timeline on TanStack Query; Knowledge upload + MCP marketplace use shared auth API helpers
- Product surface: Portrait → Memories tab; TrustReport → Dashboard tab; fix useDashboard render-time addError
- Settings: Query migration, capability-policy API (trust UI from JSON), surface silent load errors
- Follow-up: taint path = settings.capability_policy_path (fail-closed); Dashboard/Trust soft-fail; MCP mesh in startup_health
- Fix notification WS envelope type; approval_changed invalidation; memory graph batched Chroma query
- goal_changed WS; async to_thread on dashboard/memory/goals/knowledge reads; SSE idle timeout during read()
