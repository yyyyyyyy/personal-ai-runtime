.PHONY: install dev test test-backend test-frontend desktop boundary rebuild-verify meaning-verify meaning-dag-verify authority-verify drift-verify trajectory-verify identity-projection-verify identity-verify agency-verify egress-verify connector-verify belief-verify belief-quality belief-survival alembic-verify vector-consistency-verify docker-up docker-down

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

test: test-backend test-frontend

test-backend:
	cd $(BACKEND_DIR) && python3 -m pytest tests/ -q

test-frontend:
	cd $(FRONTEND_DIR) && npx tsc --noEmit

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

experimental-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_meaning_boundary.py && python3 scripts/verify_trajectory.py

meaning-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_meaning_boundary.py

meaning-dag-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_meaning_dag.py

authority-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_claim_authority.py

drift-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_identity_drift.py

trajectory-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_trajectory.py

trajectory-rebuild-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_trajectory_rebuild.py

identity-projection-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_identity_projection.py

identity-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_identity.py

agency-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_agency_surfaces.py

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
