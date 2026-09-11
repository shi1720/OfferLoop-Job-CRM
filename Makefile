# OfferLoop developer entry points.

.PHONY: install dev api web test lint build docker docker-run

install:            ## install backend + frontend dependencies
	cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

api:                ## run the API (demo mode) on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web:                ## run the frontend dev server on :5173 (proxies /api)
	cd frontend && npm run dev

dev:                ## run API + frontend together
	$(MAKE) -j2 api web

test:               ## backend + frontend test suites
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm test

lint:               ## ruff + tsc
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npx tsc --noEmit

tour:               ## Playwright end-to-end tour (run `make api` first)
	cd e2e && npm install && npx playwright install chromium && npm run tour

build:              ## production frontend bundle
	cd frontend && npm run build

docker:             ## build the Cloud Run container image
	docker build -t offerloop .

docker-run:         ## run the container locally in demo mode on :8080
	docker run --rm -p 8080:8080 -e OFFERLOOP_APP_MODE=demo offerloop
