#!/usr/bin/env bash
set -euo pipefail

echo "==> Syncing dependencies"
uv sync --extra dev

echo "==> Running tests"
uv run pytest -q

echo "==> Running lint"
uv run ruff check .

echo "==> Validating Docker Compose"
docker compose config --quiet

echo "==> Verification complete"
