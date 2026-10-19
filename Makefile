.PHONY: setup dev-api dev-web build serve test

setup:
	python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

# Run these two in separate terminals during development.
dev-api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && npm run dev

# Production-style: build the React app, then FastAPI serves it on one port.
build:
	cd frontend && npm run build

serve: build
	cd backend && .venv/bin/uvicorn app.main:app --port 8000

test:
	cd backend && .venv/bin/pytest -q
