#!/usr/bin/env bash
# Run the backend test suite inside Docker (clean Python 3.13 + ffmpeg environment).
#
# Uses a SEPARATE compose project with its own containers and volumes, so it never
# touches (or recreates) the development or production stack, and is torn down
# afterwards. Extra args are passed to pytest:
#   scripts/test.sh            # whole suite
#   scripts/test.sh -k auth    # subset
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="youtube-clone-test"
compose() { docker compose -p "$PROJECT" --profile test "$@"; }
trap 'compose down -v --remove-orphans >/dev/null 2>&1 || true' EXIT

compose build backend-tests
compose run --rm backend-tests python -m pytest -q "$@"
