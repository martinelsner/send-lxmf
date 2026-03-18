VENV = .venv

.PHONY: help venv install test build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

venv: ## Create a virtual environment
	uv venv --allow-existing $(VENV)

install: venv ## Install the project in editable mode with dev deps
	uv pip install --python $(VENV)/bin/python -e ".[dev]"

test: install ## Run the test suite
	$(VENV)/bin/pytest tests/

build: install ## Build sdist and wheel for PyPI
	uv build

clean: ## Remove the venv and build artifacts
	rm -rf $(VENV) *.egg-info src/*.egg-info dist/ result
