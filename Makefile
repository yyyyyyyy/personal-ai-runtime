.PHONY: install setup init-db dev demo screenshots test test-backend test-backend-coverage test-frontend test-e2e test-e2e-real ci-local backend-ci-core backend-ci-static backend-ci-runtime backend-compileall backend-smoke lint typecheck dependency-sync desktop desktop-test desktop-build boundary layer-deps layer-deps-inventory layer-deps-strict docs-links docs-table-sync docs-line-refs policy-consistency rebuild-verify export-roundtrip-verify snapshot-verify egress-verify connector-verify alembic-verify vector-consistency-verify memory-repair-verify tool-calls-audit-verify architecture-check architecture-check-strict architecture-snapshot architecture-record event-schema event-schema-snapshot event-schema-record non-sovereign-attachments single-process-control-plane dynamic-imports dashboard dashboard-write docker-up docker-down projection-provenance conversation-rebuild goal-rebuild work-items-goal-rebuild memory-lifecycle-verify inbox-audit-verify lockfile secrets-scan

# Backend
BACKEND_DIR := backend
FRONTEND_DIR := frontend
DESKTOP_DIR := desktop

# Parallelism for layered CI (override: make backend-ci-core JOBS=8)
JOBS ?= $(shell getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)

install: dependency-sync
	cd $(BACKEND_DIR) && python3 -m pip install --require-hashes -r requirements.lock
	cd $(FRONTEND_DIR) && npm ci
	cd $(DESKTOP_DIR) && npm ci
	cd $(DESKTOP_DIR) && python3 generate_icon.py
	cd $(BACKEND_DIR) && python3 -m alembic upgrade head 2>/dev/null || echo "DB will auto-init on first run"

# Full interactive setup (configuration guide + deps + DB init)
setup:
	bash install.sh

init-db:
	cd $(BACKEND_DIR) && python3 -m alembic upgrade head 2>/dev/null || echo "DB will auto-init on first run"

install-hooks:
	bash scripts/install_hooks.sh

dev:
	@echo "Starting backend (8000), waiting for health, then frontend (5173)..."
	@(cd $(BACKEND_DIR) && python3 -m uvicorn app.main:app --reload --port 8000) & \
	bash scripts/wait_for_health.sh localhost 8000 60 && \
	(cd $(FRONTEND_DIR) && npm run dev) & \
	wait

demo:
	cd $(BACKEND_DIR) && LLM_API_KEY=$${LLM_API_KEY:-demo-seed} python3 -m scripts.seed_demo

screenshots:
	cd docs/assets && npm install && npx playwright install chromium && npm run screenshots

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && python3 -m pytest tests/ -q -m "not live_llm"

test-backend-coverage:
	cd $(BACKEND_DIR) && python3 -m pytest tests/ -v --cov=app/core/runtime --cov=app/core/harness --cov=app/api --cov-report=term-missing -m "not live_llm"
	cd $(BACKEND_DIR) && python3 -m coverage report --include='app/core/runtime/*' --fail-under=75
	cd $(BACKEND_DIR) && python3 -m coverage report --include='app/api/*' --fail-under=50

test-frontend:
	cd $(FRONTEND_DIR) && npx tsc --noEmit && npm test

test-e2e:
	cd $(FRONTEND_DIR) && npx playwright install chromium && npm run test:e2e

lint:
	cd $(BACKEND_DIR) && ruff check app/

typecheck:
	cd $(BACKEND_DIR) && python3 -m mypy app/ scripts/ --ignore-missing-imports

dependency-sync:
	cd $(BACKEND_DIR) && python3 -m scripts.check_dependency_sync

# Static checks — no shared DB; safe to run in parallel.
BACKEND_CI_STATIC := dependency-sync backend-compileall lint typecheck version-sync \
	policy-consistency docs-links docs-table-sync docs-line-refs boundary \
	layer-deps execution-ownership architecture-check event-schema \
	non-sovereign-attachments single-process-control-plane dynamic-imports

# Runtime verifies — ephemeral DBs / tmp paths; parallel after static wave.
BACKEND_CI_RUNTIME := alembic-verify backend-smoke test-backend-coverage \
	projection-provenance rebuild-verify snapshot-verify conversation-rebuild \
	goal-rebuild work-items-goal-rebuild export-roundtrip-verify \
	memory-lifecycle-verify inbox-audit-verify egress-verify connector-verify \
	vector-consistency-verify memory-repair-verify tool-calls-audit-verify

BACKEND_CI_TARGETS := $(BACKEND_CI_STATIC) $(BACKEND_CI_RUNTIME)

backend-ci-static: $(BACKEND_CI_STATIC)
	@echo "backend-ci-static checks passed"

backend-ci-runtime: $(BACKEND_CI_RUNTIME)
	@echo "backend-ci-runtime checks passed"

# Two-wave parallel CI: static first (no shared process state), then runtime.
# Runtime jobs use per-script ephemeral/tmp DBs; safe to -j within the wave.
backend-ci-core:
	$(MAKE) -j$(JOBS) backend-ci-static
	$(MAKE) -j$(JOBS) backend-ci-runtime
	@echo "backend-ci-core checks passed"

ci-local: backend-ci-core test-frontend test-e2e test-e2e-real desktop-test
	@echo "ci-local checks passed"

test-e2e-real:
	cd $(FRONTEND_DIR) && npx playwright install chromium && npm run test:e2e:real

backend-compileall:
	cd $(BACKEND_DIR) && python3 -m compileall app/ -q

backend-smoke:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_api_mcp_smoke

desktop:
	cd $(DESKTOP_DIR) && npm start

desktop-test:
	cd $(DESKTOP_DIR) && npm test

desktop-build:
	cd $(DESKTOP_DIR) && npm run build

boundary:
	cd $(BACKEND_DIR) && python3 -m scripts.check_boundary

layer-deps:
	cd $(BACKEND_DIR) && python3 -m scripts.check_layer_deps

layer-deps-inventory:
	cd $(BACKEND_DIR) && python3 -m scripts.check_layer_deps --inventory

layer-deps-strict:
	cd $(BACKEND_DIR) && python3 -m scripts.check_layer_deps --strict

docs-links:
	cd $(BACKEND_DIR) && python3 -m scripts.check_doc_links

docs-table-sync:
	cd $(BACKEND_DIR) && python3 -m scripts.check_doc_table_sync

docs-line-refs:
	cd $(BACKEND_DIR) && python3 -m scripts.check_doc_line_refs

policy-consistency:
	cd $(BACKEND_DIR) && python3 -m scripts.check_capability_policy_consistency

version-sync:
	cd $(BACKEND_DIR) && python3 -m scripts.check_version_sync

boundary-inventory:
	cd $(BACKEND_DIR) && python3 -m scripts.check_boundary --inventory

boundary-strict:
	cd $(BACKEND_DIR) && python3 -m scripts.check_boundary --strict

execution-ownership:
	cd $(BACKEND_DIR) && python3 -m scripts.check_execution_ownership

execution-ownership-inventory:
	cd $(BACKEND_DIR) && python3 -m scripts.check_execution_ownership --inventory

execution-ownership-strict:
	cd $(BACKEND_DIR) && python3 -m scripts.check_execution_ownership --strict

# Architecture Contract — enforces runtime-algebra.md §5.2 (Concept Compression)
architecture-check:
	cd $(BACKEND_DIR) && python3 -m scripts.check_concept_growth

architecture-check-strict:
	cd $(BACKEND_DIR) && python3 -m scripts.check_concept_growth --strict

architecture-snapshot:
	cd $(BACKEND_DIR) && python3 -m scripts.check_concept_growth --snapshot

architecture-record:
	cd $(BACKEND_DIR) && python3 -m scripts.check_concept_growth --record

event-schema:
	cd $(BACKEND_DIR) && python3 -m scripts.check_event_schema

event-schema-snapshot:
	cd $(BACKEND_DIR) && python3 -m scripts.check_event_schema --snapshot

event-schema-record:
	cd $(BACKEND_DIR) && python3 -m scripts.check_event_schema --record

non-sovereign-attachments:
	cd $(BACKEND_DIR) && python3 -m scripts.check_non_sovereign_attachments

single-process-control-plane:
	cd $(BACKEND_DIR) && python3 -m scripts.check_single_process_control_plane

dynamic-imports:
	cd $(BACKEND_DIR) && python3 -m scripts.check_dynamic_imports

dashboard:
	cd $(BACKEND_DIR) && python3 -m scripts.health_dashboard

dashboard-write:
	cd $(BACKEND_DIR) && python3 -m scripts.health_dashboard --write

projection-provenance:
	cd $(BACKEND_DIR) && python3 -m scripts.check_projection_provenance

conversation-rebuild:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_conversation_rebuild

goal-rebuild:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_goal_rebuild

work-items-goal-rebuild:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_work_items_goal_rebuild

rebuild-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_rebuild

export-roundtrip-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_export_roundtrip

snapshot-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_snapshot_rebuild

egress-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_egress

vector-consistency-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_vector_consistency

connector-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_connector

memory-lifecycle-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_memory_lifecycle

inbox-audit-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_inbox_audit

memory-repair-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_memory_index_repairs

tool-calls-audit-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_tool_calls_audit

alembic-verify:
	cd $(BACKEND_DIR) && python3 -m scripts.verify_alembic

docker-up:
	docker compose up --build

docker-down:
	docker compose down

lockfile:
	cd $(BACKEND_DIR) && python3 -c "import piptools" 2>/dev/null || python3 -m pip install --user pip-tools==7.5.3
	cd $(BACKEND_DIR) && python3 -m piptools compile --generate-hashes --output-file requirements.lock requirements-dev.txt
	cd $(BACKEND_DIR) && python3 -m scripts.check_dependency_sync --stamp-lock
	@echo "Created backend/requirements.lock — commit it for reproducible installs."

secrets-scan:
	@gitleaks detect --config .gitleaks.toml --source . --no-banner --redact || \
		echo "gitleaks not installed — install from https://github.com/gitleaks/gitleaks"
