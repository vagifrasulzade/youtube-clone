# Testing

## How to run

```bash
# backend: needs the dev infrastructure (postgres, redis, minio + minio-init)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio minio-init
cd backend && venv/bin/python -m pytest -q            # Windows: venv\Scripts\python

# backend in a clean, isolated container (own compose project and volumes)
scripts/test.sh

# frontend
cd frontend && npm test && npm run lint && npm run build

# end-to-end against a deployed stack (through nginx)
scripts/smoke_test.sh
```

CI (`.github/workflows/ci.yml`) runs the backend job (ruff + pytest with real PostgreSQL, Redis and a provisioned MinIO) and the frontend job (ESLint, Vitest, type-checked build) on every push.

## Principles

- **Real dependencies.** Integration tests hit PostgreSQL, Redis and MinIO; nothing in the storage or database path is mocked. Uploads go to MinIO with real presigned POST policies, so size/key/type limits are proven to be enforced by storage itself.
- **The database is built from migrations** at the start of every run; `alembic check` proves models and migrations do not drift.
- **Isolation:** each test runs in a transaction rolled back at the end (savepoint mode); Redis uses a dedicated logical DB flushed per test; storage objects are removed by a fixture.
- **Negative cases first-class:** every protected route has 401/403/404 tests; private videos are checked on every route that could leak them.
- **Never claim an unrun result** (CLAUDE.md): reported numbers come from actual runs.

## Acceptance criteria → tests

| Criterion | Tests (backend unless noted) |
|---|---|
| A1 upload works end-to-end | `test_uploads.py::test_upload_roundtrip_queues_processing` (processing step: pending task) |
| A2 size limit enforced by storage | `test_uploads.py::test_storage_rejects_a_file_larger_than_the_policy_allows`, tampered key/content type tests |
| A3 non-video never published | `test_uploads.py::test_a_non_video_file_fails_with_a_readable_reason` |
| A5 no orphans | `test_maintenance.py` (stale drafts, idempotent object deletion) |
| A6 duplicate processing harmless | watchdog / claim logic in `test_maintenance.py` (task itself pending) |
| B1 Range 206 | `test_media.py::test_range_requests_return_206_with_exact_bytes`, 416 test |
| B2 no storage URLs | `test_uploads.py::test_api_responses_never_expose_the_storage_endpoint`, `test_media.py` accel/detail tests |
| C1–C5 visibility | `unit/test_access_policy.py` (truth table), `test_media.py`, `test_private_grants.py`, `test_feeds.py`, `test_search.py`, `test_playlists.py` |
| D1 reactions/counters | `test_reactions.py` (counters equal row counts after every step) |
| D3 subscriptions | `test_subscriptions.py` |
| D4 views once per 24 h | `test_views_history.py` |
| E1–E5 auth | `test_auth.py`, `unit/test_security.py`, `unit/test_config.py`, `test_roles.py`, `test_admin.py` |
| F1 deploy | `scripts/smoke_test.sh` on the running stack (+ manual checks recorded in [ai-workflow.md](ai-workflow.md#4-verification-evidence)) |
| DB guarantees | `test_schema_constraints.py` (each constraint asserted by name), `test_migrations.py` |
| Frontend | `VideoCard.test.tsx`, `SearchBox.test.tsx`, `http.test.ts`, `duration.test.ts` |

## Numbers (latest run)

- Backend: **346 passed** (26 test modules).
- Frontend: **17 passed** (4 test files).

## Known gaps

- The `process_video` Celery task and the comments API are not implemented yet (see [ai-workflow.md § 7](ai-workflow.md#7-what-did-not-go-to-plan-honestly)); their tests are part of that work. The smoke test therefore stops at the processing step.
- No browser end-to-end tests (Playwright) yet; frontend tests are component-level.
