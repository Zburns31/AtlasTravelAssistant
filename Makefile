.PHONY: dev api web install

# Run both FastAPI backend (:8000) and Next.js frontend (:3000) together.
# Ctrl-C stops both processes cleanly.
dev:
	@echo "Starting Atlas (API :8000 + Web :3000)..."
	@trap 'kill 0' INT TERM EXIT; \
		uv run atlas-api & \
		pnpm --dir web dev & \
		wait

api:
	uv run atlas-api

web:
	pnpm --dir web dev

install:
	uv sync --extra web
	pnpm --dir web install
