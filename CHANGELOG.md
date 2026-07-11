# Changelog

All notable changes to Personal AI Runtime are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/). Version numbers match [`backend/app/version.py`](backend/app/version.py).

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
