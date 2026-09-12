# CVA — convenience targets. Run `make help` for the list.
# Autonomous runs need TARGET set to an authorized target you control:
#   make auto TARGET=<target-url>
.DEFAULT_GOAL := help
TARGET ?=

.PHONY: help install test kb demo run auto up down clean require-target

require-target:
	@[ -n "$(TARGET)" ] || { echo "Set TARGET=<target-url> (an authorized target you control)"; exit 1; }

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies into .venv
	uv sync

test: ## Run the test suite
	uv run pytest tests/ -q

kb: ## Build/refresh the FTS5 knowledge base
	uv run python scripts/ingest_kb.py

demo: require-target ## One-command demo against your target (make demo TARGET=<target-url>)
	./demo.sh $(TARGET)

run: ## Start the interactive assistant (copilot mode)
	uv run python main.py

auto: require-target ## Autonomous run against your target (make auto TARGET=<target-url>)
	uv run python cva.py --auto $(TARGET)

up: ## Start MongoDB (session persistence)
	docker compose up -d

down: ## Stop docker services
	docker compose down

clean: ## Remove caches and build artifacts (keeps the KB index)
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
