#!/usr/bin/env bash
# Run the backend test suite inside the API Docker image (matches production deps).
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose run --rm \
  -v "$(pwd)/tests:/app/tests:ro" \
  -v "$(pwd)/pytest.ini:/app/pytest.ini:ro" \
  api sh -c "pip install -q -r requirements.txt pytest && python -m pytest tests/ -v \"\$@\"" -- "$@"
