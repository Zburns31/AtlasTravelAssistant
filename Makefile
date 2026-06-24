.PHONY: dev api web install

ENV_LOAD = set -a; . ./.env; set +a;

# Run both FastAPI backend (:8000) and Next.js frontend (:3000) together.
# Ctrl-C stops both processes cleanly.
dev:
	@echo "Starting Atlas (API :8000 + Web :3000)..."
	@trap 'kill 0' INT TERM EXIT; \
		$(ENV_LOAD) uv run atlas-api & \
		$(ENV_LOAD) pnpm --dir web dev & \
		wait

api:
	@$(ENV_LOAD) uv run atlas-api

web:
	@$(ENV_LOAD) pnpm --dir web dev

install:
	uv sync --extra web
	pnpm --dir web install
