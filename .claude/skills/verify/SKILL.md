---
name: verify
description: Run every quality gate (ruff lint/format, the pytest suite, frontend type-check/lint/build when the frontend changed) and report the real results. Use before every commit and whenever asked whether something works.
---

# Verify the working tree

1. Make sure the dev infrastructure is up:
   `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio`
2. Backend (cwd `backend/`, using the venv interpreter):
   - `python -m ruff check .`
   - `python -m ruff format --check .`
   - `python -m pytest -q`
3. Frontend (only if `frontend/` changed; cwd `frontend/`):
   - `npx tsc -b --noEmit` (or `npm run build`)
   - `npm run lint`

## Report
- Quote the **actual** final summary line of each command (e.g. `42 passed in 3.10s`).
- For any failure, show the relevant error output and name the cause. Do not summarize a failure as a success, and do not say "should pass".
- If a gate could not be run (e.g. Docker is down), say exactly which one and why. That counts as **not verified**.
