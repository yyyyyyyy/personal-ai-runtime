.PHONY: install setup init-db dev demo screenshots test test-backend test-backend-coverage test-frontend test-e2e test-e2e-real ci-local backend-ci-core backend-compileall backend-smoke lint typecheck dependency-sync desktop desktop-test desktop-build boundary docs-links docs-table-sync docs-line-refs policy-consistency rebuild-verify export-roundtrip-verify snapshot-verify egress-verify connector-verify alembic-verify vector-consistency-verify memory-repair-verify architecture-check architecture-check-strict architecture-snapshot architecture-record dashboard dashboard-write docker-up docker-down projection-provenance conversation-rebuild goal-rebuild work-items-goal-rebuild memory-lifecycle-verify inbox-audit-verify lockfile secrets-scan

# Backend
BACKEND_DIR := backend
FRONTEND_DIR := frontend
DESKTOP_DIR := desktop

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
	cd $(BACKEND_DIR) && LLM_API_KEY=$${LLM_API_KEY:-demo-seed} python3 scripts/seed_demo.py

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

AGENTS_MYPY := app/core/agents/brain.py app/core/agents/conversation.py app/core/agents/llm_failover.py app/core/agents/memory_engine.py app/core/agents/memory_extractor.py

typecheck:
	cd $(BACKEND_DIR) && mypy app/ scripts/ --ignore-missing-imports

dependency-sync:
	cd $(BACKEND_DIR) && python3 scripts/check_dependency_sync.py

BACKEND_CI_TARGETS := dependency-sync backend-compileall lint typecheck test-backend-coverage \
	alembic-verify backend-smoke version-sync policy-consistency docs-links docs-table-sync \
	docs-line-refs boundary execution-ownership architecture-check projection-provenance \
	rebuild-verify snapshot-verify conversation-rebuild goal-rebuild work-items-goal-rebuild \
	export-roundtrip-verify memory-lifecycle-verify inbox-audit-verify egress-verify \
	connector-verify vector-consistency-verify memory-repair-verify

backend-ci-core: $(BACKEND_CI_TARGETS)
	@echo "backend-ci-core checks passed"

ci-local: backend-ci-core test-frontend test-e2e test-e2e-real desktop-test
	@echo "ci-local checks passed"

test-e2e-real:
	cd $(FRONTEND_DIR) && npx playwright install chromium && npm run test:e2e:real

backend-compileall:
	cd $(BACKEND_DIR) && python3 -m compileall app/ -q

backend-smoke:
	cd $(BACKEND_DIR) && python3 scripts/verify_api_mcp_smoke.py

desktop:
	cd $(DESKTOP_DIR) && npm start

desktop-test:
	cd $(DESKTOP_DIR) && npm test

desktop-build:
	cd $(DESKTOP_DIR) && npm run build

boundary:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py

docs-links:
	cd $(BACKEND_DIR) && python3 scripts/check_doc_links.py

docs-table-sync:
	cd $(BACKEND_DIR) && python3 scripts/check_doc_table_sync.py

docs-line-refs:
	cd $(BACKEND_DIR) && python3 scripts/check_doc_line_refs.py

policy-consistency:
	cd $(BACKEND_DIR) && python3 scripts/check_capability_policy_consistency.py

version-sync:
	cd $(BACKEND_DIR) && python3 scripts/check_version_sync.py

boundary-inventory:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py --inventory

boundary-strict:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py --strict

execution-ownership:
	cd $(BACKEND_DIR) && python3 scripts/check_execution_ownership.py

execution-ownership-inventory:
	cd $(BACKEND_DIR) && python3 scripts/check_execution_ownership.py --inventory

execution-ownership-strict:
	cd $(BACKEND_DIR) && python3 scripts/check_execution_ownership.py --strict

# Architecture Contract — enforces runtime-algebra.md §5.2 (Concept Compression)
# Fails CI when any concept metric grows (files, event types, fragments, tables,
# projectors, God-Object LOC, dead-code files).
architecture-check:
	cd $(BACKEND_DIR) && python3 scripts/check_concept_growth.py

architecture-check-strict:
	cd $(BACKEND_DIR) && python3 scripts/check_concept_growth.py --strict

architecture-snapshot:
	cd $(BACKEND_DIR) && python3 scripts/check_concept_growth.py --snapshot

architecture-record:
	cd $(BACKEND_DIR) && python3 scripts/check_concept_growth.py --record

dashboard:
	cd $(BACKEND_DIR) && python3 scripts/health_dashboard.py

dashboard-write:
	cd $(BACKEND_DIR) && python3 scripts/health_dashboard.py --write

projection-provenance:
	cd $(BACKEND_DIR) && python3 scripts/check_projection_provenance.py

conversation-rebuild:
	cd $(BACKEND_DIR) && python3 scripts/verify_conversation_rebuild.py

goal-rebuild:
	cd $(BACKEND_DIR) && python3 scripts/verify_goal_rebuild.py

work-items-goal-rebuild:
	cd $(BACKEND_DIR) && python3 scripts/verify_work_items_goal_rebuild.py

rebuild-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_rebuild.py

export-roundtrip-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_export_roundtrip.py

snapshot-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_snapshot_rebuild.py

egress-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_egress.py

vector-consistency-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_vector_consistency.py

connector-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_connector.py

memory-lifecycle-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_memory_lifecycle.py

inbox-audit-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_inbox_audit.py

memory-repair-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_memory_index_repairs.py

# Alembic schema migration
alembic-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_alembic.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

# Generate a pinned, hash-verified lockfile from runtime and development inputs.
# Commit backend/requirements.lock so CI installs exactly the same versions.
lockfile:
	cd $(BACKEND_DIR) && python3 -c "import piptools" 2>/dev/null || python3 -m pip install --user pip-tools==7.5.3
	cd $(BACKEND_DIR) && python3 -m piptools compile --generate-hashes --output-file requirements.lock requirements-dev.txt
	cd $(BACKEND_DIR) && python3 scripts/check_dependency_sync.py --stamp-lock
	@echo "Created backend/requirements.lock — commit it for reproducible installs."

# Scan the working tree for leaked secrets using gitleaks.
# Install via: brew install gitleaks (macOS) or see https://github.com/gitleaks/gitleaks
secrets-scan:
	@gitleaks detect --config .gitleaks.toml --source . --no-banner --redact || \
		echo "gitleaks not installed — install from https://github.com/gitleaks/gitleaks"
