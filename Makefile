.PHONY: help install sync lint format format-check typecheck test test-cov check pre-commit clean

UV ?= uv
SRC := src
PKG := src/pycommon
TESTS := tests

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\n"} \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install all + dev extras (uv sync)
	$(UV) sync --extra all --extra dev

sync: install ## Alias for install

lint: ## Ruff lint (src + tests)
	$(UV) run ruff check $(SRC) $(TESTS)

format: ## Ruff format (write)
	$(UV) run ruff format $(SRC) $(TESTS)

format-check: ## Ruff format check (CI)
	$(UV) run ruff format --check $(SRC) $(TESTS)

typecheck: ## Mypy strict on package
	$(UV) run python -m mypy $(PKG)

test: ## Pytest
	$(UV) run python -m pytest

test-cov: ## Pytest with coverage
	$(UV) run python -m pytest --cov=pycommon --cov-report=term-missing

check: lint format-check typecheck test ## Run full CI checks locally

pre-commit: ## Install + run pre-commit hooks
	$(UV) run pre-commit install
	$(UV) run pre-commit run --all-files

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find $(SRC) $(TESTS) -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find $(SRC) $(TESTS) -type f -name '*.py[co]' -delete 2>/dev/null || true
