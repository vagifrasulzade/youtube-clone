#!/usr/bin/env bash
# Run the backend test suite inside Docker (clean Python 3.13 environment),
# against the stack's PostgreSQL and Redis. Extra args are passed to pytest.
#   scripts/test.sh            # whole suite
#   scripts/test.sh -k auth    # subset
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d --wait postgres redis minio
docker compose --profile test build backend-tests
docker compose --profile test run --rm backend-tests python -m pytest -q "$@"
