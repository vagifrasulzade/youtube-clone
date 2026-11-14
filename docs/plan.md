# Implementation plan

> **Status: Approved — Stage 1, 2026-11-14.** Order agreed with the architect: **backend first, then frontend.** Day 1 = 2026-11-14, Day 10 = 2026-11-23.

## 1. Roadmap (10 days)

Each day ends with green tests, a review of the diff and commits. The "exit criteria" column is what has to be *demonstrated* (real command output), not claimed.

| Day | Date | Stage | Deliverables | Exit criteria |
|---|---|---|---|---|
| 1 | 11-14 | **1** + 2a | This design (approved) · repo hygiene · `CLAUDE.md` + `.claude/` · backend skeleton: settings, DB session, app factory, error envelope, logging, health · dev compose (postgres, redis, minio) · pytest harness · CI workflow | `pytest` green in Docker (health + DB connectivity), `ruff` clean |
| 2 | 11-15 | 2b + **3** | All models + initial Alembic migration · auth: register / login / refresh / logout / me / change-password · Argon2id · JWT · RBAC dependencies · Redis rate limiter | Migration up → down → up on an empty DB · auth tests for E1–E5 green |
| 3 | 11-16 | **4** | S3 adapter · `minio-init` (buckets, lifecycle, app user) · draft creation + presigned POST + upload-complete · image uploads (thumbnail / avatar / banner, re-encode) | An integration test performs a **real presigned POST to MinIO**. An oversize file is rejected *by MinIO* (A2) |
| 4 | 11-17 | **5** | Celery worker + beat · ffmpeg pipeline (probe, remux/transcode, thumbnails, progress) · state machine, watchdog, cleanup · access policy · media endpoints (X-Accel + proxy fallback, Range) | A generated test clip goes through to `ready` (A1, A6). A fake file is `failed` (A3). A Range request gives `206` (B1). Access matrix tests (C1–C5) |
| 5 | 11-18 | **6** + 7a | Reactions · comments + replies · views + history · subscriptions + subscription feed · playlists · search (FTS + trigram) + suggestions · related | D1–D4 tests, search tests, counter == row-count assertions |
| 6 | 11-19 | 7b + 10a | Reports · moderation actions + audit · admin APIs · **full production compose** (nginx, api, worker, beat, migrate, minio-init) · `deploy.sh` v1 · seed script · `smoke_test.sh` · security review #1 | `./deploy.sh` in a clean Ubuntu VM → smoke test green (F1, early) · backend feature-complete |
| 7 | 11-20 | **8a** | Frontend foundation: router, layout (header, sidebar, mini sidebar, mobile drawer), auth pages + token refresh, generated API types, Home feed, VideoCard, skeletons | Side-by-side visual check against YouTube · `tsc` + `eslint` clean |
| 8 | 11-21 | 8b | Watch page (player, actions, description, comments, related, subscribe) · Channel page (banner, tabs) · Search (results, sort, pagination, suggestions) | Manual walkthrough on the deployed stack · vitest for formatters and the auth interceptor |
| 9 | 11-22 | 8c | Upload dialog (drop → progress → details → thumbnail → visibility → processing status) · Studio (table, edit, delete, share private) · playlists UI · History / Liked / Subscriptions · Moderation + Admin dashboards | Full scenario in a browser: register → upload → watch → like → comment → report → moderate |
| 10 | 11-23 | **9** + 10b | Security review #2 + fixes · final clean-Ubuntu deploy test · README + `deployment.md` + `testing.md` + `ai-workflow.md` · export AI sessions · zip | Every criterion A–F ticked with evidence (test name or command output) |

**Biggest schedule risk:** with backend first, the UI (graded on looking like YouTube) gets Days 7–9.
Mitigations:
1. The API contract is fixed now ([api.md](api.md)), and frontend types are generated from OpenAPI.
2. Demo data exists from Day 6, so the UI is built against realistic content.
3. **Cut list**, cut in this order if late: playlist reordering → History → search suggestions → comment editing → Shared-with-me page. The core scenario, upload flow and moderation are never cut.

## 2. Testing strategy

| Level | Tooling | What | Runs |
|---|---|---|---|
| Unit | pytest | Password hashing, JWT encode/decode/expiry/typ confusion, the **access policy matrix** (table-driven), keyset cursor encoding, ffmpeg argument building, magic-byte sniffing | Every change |
| Integration (API) | pytest + FastAPI `TestClient` against **real PostgreSQL, Redis, MinIO** (compose test profile) | Every endpoint group; positive and **negative** authorization cases | Every change, CI |
| Worker | pytest + real ffmpeg | A 2-second clip generated at fixture time (`ffmpeg -f lavfi testsrc`) → `ready`. Text renamed to `.mp4` → `failed`. Double delivery → one processing run | Every change, CI |
| Smoke / E2E (deploy) | `scripts/smoke_test.sh` (curl + jq) | Against the deployed nginx: register → login → upload (real presigned POST) → wait for `ready` → `Range` request gives `206` → like → comment → verify counts | After every deploy, and at the end of `deploy.sh` (optional flag) |
| Frontend | vitest + Testing Library, `tsc`, `eslint` | Formatters, the auth interceptor (single-flight refresh), route guards | Every frontend change, CI |

Test isolation: each test runs inside a transaction rolled back by savepoint (SQLAlchemy 2.0 "join into external transaction" pattern). Redis uses a dedicated DB that is flushed per test, and MinIO uses per-run bucket names.

Priority tests (from the brief), each named after its acceptance criterion:
- `test_register_login_refresh_logout`, `test_refresh_token_reuse_revokes_family` (E1, E2)
- `test_upload_presigned_post_roundtrip`, `test_oversize_rejected_by_storage` (A1, A2)
- `test_processing_ready`, `test_fake_video_fails`, `test_duplicate_task_is_noop` (A1, A3, A6)
- `test_owner_only_can_edit_and_delete` (ownership)
- `test_private_video_matrix`: guest / user / granted / owner / moderator / admin × detail / stream / thumbnail / comments / reactions (C1–C5)
- `test_public_video_access`, `test_unlisted_not_listed`, `test_range_request_206` (C1, C3, B1)
- `test_like_switch_dislike_counters`, `test_comments_permissions`, `test_subscribe_idempotent_and_not_self` (D1–D3)
- `test_moderator_can_hide_cannot_manage_users`, `test_admin_guardrails` (E4)
- `test_unauthenticated_protected_endpoints_401` (parametrized over the route table), `test_login_rate_limited` (E5)

Rule: **a test result is only reported if it was actually run**, and its output is shown.

## 3. Git workflow

- **Conventional Commits** with scopes: `feat(backend)`, `feat(frontend)`, `feat(db)`, `build(infra)`, `test(backend)`, `docs`, `chore(ai)`, `fix(…)`, `refactor(…)`.
- Small commits: one logical change each, and the build and tests pass at every commit.
- One branch per stage (`stage/2-backend-foundation`, `stage/3-auth`, …), merged into `main` with `--no-ff` so the history shows the stage structure, and a tag `stage-N` after each merge. `v1.0.0` at submission.
- History is never rewritten after it is pushed. `.env` and secrets are never committed.

**Commit plan for the start** (in order):

1. `chore: add root .gitignore and untrack committed bytecode`
2. `docs: add architecture, database, API, storage, security design and plan`
3. `chore(ai): add CLAUDE.md, Claude Code settings, agents and skills`
4. `chore(ai): save master prompts verbatim`
5. `build(backend): pin dependencies and replace passlib/python-jose with argon2-cffi/PyJWT`
6. `build(infra): add dev docker compose for postgres, redis and minio`
7. `feat(backend): add settings, database session and app factory`
8. `feat(backend): add error envelope, request id logging and health endpoints`
9. `test(backend): set up pytest with transactional postgres fixtures`
10. `ci: run lint and backend tests on push`
11. `feat(db): add initial schema migration` (Day 2) → then `feat(backend): implement registration and login`, …

## 4. AI workflow and agent setup

| Piece | Purpose |
|---|---|
| `CLAUDE.md` | Stack, commands (test, lint, run), layering rules (§ 2.4 of architecture.md), the access-policy rule, the definition of done, git conventions, and forbidden shortcuts (fake implementations, unrun test claims, TODOs in critical paths, committing secrets) |
| `.claude/settings.json` | Allow: pytest, ruff, docker compose, read-only git, npm scripts. Deny: reading `.env`, `git push --force`, `rm -rf`. A hook runs `ruff format` on edited Python files |
| `.claude/agents/code-reviewer.md` | Reviews each stage diff against CLAUDE.md: layering, correctness, test coverage of acceptance criteria |
| `.claude/agents/security-reviewer.md` | Checks every new endpoint for authentication, the access policy, IDOR, mass assignment, validation, rate limits and storage exposure |
| `.claude/agents/test-engineer.md` | Writes the negative and edge-case tests for a feature, from its acceptance criteria |
| `.claude/skills/stage`, `verify`, `commit` | Repeatable workflows: run a stage (analyze → plan → implement → test → review → docs), run all checks and report the real output, and make a conventional commit of a reviewed change |
| `ai/prompts/` | The prompts given to the AI, saved verbatim |
| `ai/sessions/` | Claude Code transcripts copied from `C:\Users\LOQ\.claude\projects\c--Users-LOQ-Desktop-youtube-clone\*.jsonl` at the end |

Per-stage loop: **analyze → small tasks → implement → run tests (real output) → reviewer agents on the diff → fix → update docs → architect approval → commit and merge.**

## 5. Current repository findings (fixed on Day 1)

| Finding | Fix |
|---|---|
| `backend/app/__pycache__/*.pyc` is committed, and there is no root `.gitignore` | Add a root `.gitignore` and run `git rm --cached` on the bytecode |
| `requirements.txt` is unpinned | Pin versions; split runtime and dev deps |
| `passlib[bcrypt]` is unmaintained and breaks with modern bcrypt; the brief asks for Argon2 | Replace with `argon2-cffi` |
| `python-jose` has known CVEs and little maintenance | Replace with `PyJWT` |
| `psycopg2-binary`, `minio` SDK | Replace with `psycopg[binary]` 3 and `boto3` (portable S3 API, presigned POST) |
| No Alembic, pytest or httpx | Add them |
| The local venv is Python 3.14 while the containers use 3.13 | Tests run inside Docker for parity; the venv is for the IDE only |
| Frontend: "Yotube" typo and Vite template assets | Replaced on Day 7 |
| Docker Desktop daemon not running; ffmpeg not installed locally | Start Docker Desktop. ffmpeg is needed only inside containers |
| MinIO stopped publishing community builds/images after 2025 (**confirmed 2026-11-14**: `minio/minio` on Docker Hub and quay.io returns "denied") | Use `cgr.dev/chainguard/minio` (MinIO RELEASE.2026-11-12 built from upstream source, patched, non-root) **pinned by digest**, overridable with `MINIO_IMAGE`. The S3 API keeps us swappable through config only |

## 6. Decisions (defaults accepted at approval, 2026-11-14; #5 still open)

| # | Proposal | Alternative |
|---|---|---|
| 1 | Moderators and admins can **view** private videos (needed to review reports on them) | Staff see only the metadata of private videos |
| 2 | A single 720p H.264 rendition; remux without re-encoding when the source is already browser-safe | 360p + 720p renditions (about 2× the processing time) |
| 3 | Upload limit 2 GiB / 2 h duration | Smaller limits for the test machine |
| 4 | Reports cover **videos** only | Also comments (+½ day) |
| 5 | Push to `origin` (GitHub) at the end of each stage | Local commits only until submission |
