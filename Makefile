# =============================================================================
# Aether-Agent v2 — developer commands
# =============================================================================
# Common workflows. All commands are idempotent and safe to re-run.
# Windows note: uses python -m so no PATH differences across shells.

.PHONY: install install-dev test test-cov lint typecheck run demo clean help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime deps
	python -m pip install -r requirements.txt

install-dev: ## Install runtime + dev deps
	python -m pip install -r requirements-dev.txt

test: ## Run tests (no coverage)
	python -m pytest tests/ -v

test-cov: ## Run tests with coverage (fail under 80% on app/core)
	python -m pytest tests/ -v --cov=app --cov-report=term-missing

lint: ## Lint + format check
	python -m ruff check app/ tests/ scripts/
	python -m ruff format --check app/ tests/ scripts/

format: ## Auto-format
	python -m ruff format app/ tests/ scripts/

typecheck: ## Static type check
	python -m mypy app/

run: ## Start dev server (http://localhost:8000)
	python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

demo: ## Run the routing demo (no server needed)
	python scripts/demo_routing.py

clean: ## Remove caches and generated artifacts
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage 2>/dev/null || true
