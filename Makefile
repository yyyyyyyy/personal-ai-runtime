.PHONY: install setup init-db dev demo screenshots test test-backend test-frontend test-e2e ci-local lint typecheck desktop desktop-build boundary rebuild-verify export-roundtrip-verify snapshot-verify egress-verify connector-verify alembic-verify vector-consistency-verify docker-up docker-down projection-provenance conversation-rebuild goal-rebuild

# Backend
BACKEND_DIR := backend
FRONTEND_DIR := frontend
DESKTOP_DIR := desktop

install:
	cd $(BACKEND_DIR) && pip install -r requirements.txt
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

test-frontend:
	cd $(FRONTEND_DIR) && npx tsc --noEmit && npm test

test-e2e:
	cd $(FRONTEND_DIR) && npx playwright install chromium && npm run test:e2e

lint:
	cd $(BACKEND_DIR) && ruff check app/

AGENTS_MYPY := app/core/agents/brain.py app/core/agents/conversation.py app/core/agents/llm_failover.py app/core/agents/memory_engine.py app/core/agents/memory_extractor.py

typecheck:
	cd $(BACKEND_DIR) && mypy app/ scripts/ --ignore-missing-imports

ci-local: lint typecheck test-backend test-frontend test-e2e boundary execution-ownership projection-provenance conversation-rebuild export-roundtrip-verify
	@echo "ci-local checks passed"

desktop:
	cd $(DESKTOP_DIR) && npm start

desktop-build:
	cd $(DESKTOP_DIR) && npm run build

boundary:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py

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

projection-provenance:
	cd $(BACKEND_DIR) && python3 scripts/check_projection_provenance.py

conversation-rebuild:
	cd $(BACKEND_DIR) && python3 scripts/verify_conversation_rebuild.py

goal-rebuild:
	cd $(BACKEND_DIR) && python3 scripts/verify_goal_rebuild.py

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

# Alembic schema migration
alembic-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_alembic.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
