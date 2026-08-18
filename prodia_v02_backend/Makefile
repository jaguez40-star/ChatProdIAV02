# ══════════════════════════════════════════════════════════════════════════════
# ProdIA V02 — Backend Makefile
# ⚠️ OPCIONAL — `make` NO está garantizado en esta máquina (P-4, verificado
# 2026-08-18). El canal CANÓNICO de estos comandos es `pnpm run lint:back` /
# `typecheck:back` / `test:back` desde la raíz del monorepo (ver package.json),
# o directamente `uv run <comando>` desde esta carpeta. Este Makefile es una
# comodidad para quien sí tenga GNU Make instalado; no lo asumas disponible.
# ══════════════════════════════════════════════════════════════════════════════

.PHONY: help lint format typecheck test test-cov clean install

PY := uv run

help:
	@echo "Backend Makefile — ProdIA V02 (canal alterno; canónico = pnpm run *:back)"
	@echo ""
	@echo "  install     uv sync --extra dev"
	@echo "  lint        ruff check ."
	@echo "  format      black ."
	@echo "  typecheck   mypy src"
	@echo "  test        pytest"
	@echo "  test-cov    pytest --cov=src --cov-report=html"
	@echo "  clean       borra caches (__pycache__, .mypy_cache, .pytest_cache, .ruff_cache)"

install:
	uv sync --extra dev

lint:
	$(PY) ruff check .
	$(PY) black --check .

format:
	$(PY) black .
	$(PY) ruff check --fix .

typecheck:
	$(PY) mypy src

test:
	$(PY) pytest

test-cov:
	$(PY) pytest --cov=src --cov-report=html --cov-report=term

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage
