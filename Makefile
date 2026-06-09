.PHONY: install dev test test-backend test-frontend desktop boundary rebuild-verify docker-up docker-down

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

rebuild-verify:
	cd $(BACKEND_DIR) && python3 scripts/verify_rebuild.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down
