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
| A1 upload works end-to-end | `test_uploads.py::test_upload_roundtrip_queues_processing`; processing with real ffmpeg in `test_processing.py` (remux of H.264, transcode to H.264 720p, thumbnails, raw upload deleted); `scripts/smoke_test.sh` upload → ready → 206 |
| A2 size limit enforced by storage | `test_uploads.py::test_storage_rejects_a_file_larger_than_the_policy_allows`, tampered key/content type tests |
| A3 non-video never published | `test_uploads.py::test_a_non_video_file_fails_with_a_readable_reason`, `test_processing.py::test_fake_media_fails_with_a_reason_and_produces_nothing`, duration limit (also when the header lies: `test_processing_failures.py::test_lying_duration_header_is_caught_on_the_output`) |
| A4 nothing listed before `ready` | `test_feeds.py::test_home_feed_excludes_everything_not_listable`, `test_search.py::test_never_returns_non_listable_videos` |
| A5 no orphans | `test_maintenance.py` (stale drafts, idempotent object deletion) |
| A6 duplicate processing harmless | `test_processing.py::test_duplicate_delivery_is_a_no_op`, `::test_only_queued_videos_are_claimed`, `::test_video_deleted_during_processing_leaves_no_output`; retries and give-up in `unit/test_process_task.py`; failure paths never stuck in `processing` (`test_processing_failures.py`); watchdog in `test_maintenance.py` |
| B1 Range 206 | `test_media.py::test_range_requests_return_206_with_exact_bytes`, 416 test |
| B2 no storage URLs | `test_uploads.py::test_api_responses_never_expose_the_storage_endpoint`, `test_media.py` accel/detail tests |
| C1–C5 visibility | `unit/test_access_policy.py` (truth table), `test_media.py`, `test_private_grants.py`, `test_feeds.py`, `test_search.py`, `test_playlists.py` |
| D1 reactions/counters | `test_reactions.py` (counters equal row counts after every step) |
| D2 comments and replies | `test_comments.py` (who may delete: author, video owner, moderator, admin; others 403; staff deletions audited; replies one level; counters equal rows; private-video comments 404; races end in 404, not 500) |
| D3 subscriptions | `test_subscriptions.py` |
| D4 views once per 24 h | `test_views_history.py` |
| E1–E5 auth | `test_auth.py`, `unit/test_security.py`, `unit/test_config.py`, `test_roles.py`, `test_admin.py` (incl. the `create_admin` CLI), `test_cli_reset_password.py` |
| F1 deploy | `scripts/smoke_test.sh` on the running stack (+ manual checks recorded in [ai-workflow.md](ai-workflow.md#4-verification-evidence)) |
| DB guarantees | `test_schema_constraints.py` (each constraint asserted by name), `test_migrations.py` |
| Demo data | `unit/test_seed_data.py` (15 valid accounts, no two videos look alike), `test_seed.py` (counters equal rows, re-run adds nothing and keeps passwords, `--refresh-media`) |
| Frontend | `VideoCard.test.tsx`, `SearchBox.test.tsx`, `http.test.ts`, `duration.test.ts`, `auth/session.test.ts` (single-flight refresh, late refresh after sign-out, start-up wait), `auth/guards.test.tsx` (route guard, open-redirect guard), `pages/AuthPages.test.tsx` (password show/hide) |

## Numbers (latest run)

- Backend: **435 passed** in Docker with ffmpeg (`scripts/test.sh`, 32 test modules). Without ffmpeg (e.g. on Windows) the 13 real-ffmpeg tests are skipped with a reason: 422 passed, 13 skipped.
- Frontend: **42 passed** (7 test files).

## Known gaps

- No browser end-to-end test suite: frontend tests are component- and module-level, and the UI was checked through builds, route checks and the API smoke test. `.mcp.json` configures Playwright MCP so an agent can click through the real UI; that is a manual check, not a CI suite.
- `deploy.sh` has not been run on a clean Ubuntu VM in this project's sessions. The stack was verified with Docker Desktop: smoke test, health checks and the production compose file.
- The comment-deletion race is tested deterministically, by acting on a stale row after another request deleted it, not with two real concurrent connections.
