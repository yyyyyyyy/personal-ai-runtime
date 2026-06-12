.PHONY: install dev demo screenshots test test-backend test-frontend ci-local desktop boundary rebuild-verify export-roundtrip-verify snapshot-verify egress-verify connector-verify belief-verify belief-quality belief-survival alembic-verify vector-consistency-verify docker-up docker-down

# Backend
BACKEND_DIR := backend
FRONTEND_DIR := frontend
DESKTOP_DIR := desktop

install:
	cd $(BACKEND_DIR) && pip install -r requirements.txt
	cd $(FRONTEND_DIR) && npm ci
	cd $(DESKTOP_DIR) && npm ci

dev:
	@echo "Starting backend (8000) and frontend (5173)..."
	@(cd $(BACKEND_DIR) && python3 -m uvicorn app.main:app --reload --port 8000) & \
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

ci-local: test-backend test-frontend boundary export-roundtrip-verify
	@echo "ci-local checks passed"

desktop:
	cd $(DESKTOP_DIR) && npm start

boundary:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py

boundary-inventory:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py --inventory

boundary-strict:
	cd $(BACKEND_DIR) && python3 scripts/check_boundary.py --strict

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

# Pattern + Belief verification suite
belief-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_pattern_idempotency.py && python3 scripts/verify_belief_pipeline.py

belief-quality:
	cd $(BACKEND_DIR) && python3 scripts/verify_belief_quality.py

belief-survival:
	cd $(BACKEND_DIR) && python3 scripts/verify_belief_survival.py

# Alembic schema migration
alembic-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_alembic.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
