# CLAUDE.md — YouTube Clone

A YouTube-like video platform built as a 10-day technical assessment (2026-11-14 → 2026-11-23).
The human is the **architect and reviewer**. Claude is the **implementer**. Work proceeds in the stages of [docs/plan.md](docs/plan.md), and each stage is reviewed before it is merged.

Design (source of truth; update it when the implementation deviates):
[architecture](docs/architecture.md) · [database](docs/database.md) · [api](docs/api.md) · [video-storage](docs/video-storage.md) · [security](docs/security.md) · [plan](docs/plan.md)

## Stack

- Backend: Python 3.12+ (containers: 3.13), FastAPI, SQLAlchemy 2.0 (sync, psycopg 3), Pydantic v2, Alembic, PyJWT, argon2-cffi, Celery + Redis, boto3 → MinIO, ffmpeg.
- Frontend: React 19, TypeScript, Vite, Tailwind v4, React Router, TanStack Query, Axios.
- Infra: Docker Compose, nginx (serves the SPA, proxies the API, X-Accel media delivery), PostgreSQL 17, Redis 7, MinIO.

## Commands

Run from the repo root unless noted. On Windows the venv interpreter is `backend/venv/Scripts/python`; on Linux it is `backend/venv/bin/python`.

```bash
# dev infrastructure on localhost: postgres :5433, redis :6380, minio :9000/:9001 (ports set in .env)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio

# backend (cwd: backend/)
python -m pip install -r requirements-dev.txt
python -m pytest                      # all tests (needs dev infrastructure)
python -m ruff check . && python -m ruff format --check .
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "<message>"   # always review the generated file
python -m uvicorn app.main:app --reload

# frontend (cwd: frontend/)
npm run dev | npm run build | npm run lint
```

## Architecture rules (do not break without updating docs/architecture.md)

1. **Layering:** `api/v1/*` routers do HTTP only (validate, call a service, map to a schema). Business rules and transactions live in `services/`. Models live in `models/`. Routers never contain authorization logic or ad-hoc queries.
2. **One video access policy:** every single-video read goes through `services/access.get_viewable_video_or_404`, and every video list through `access.listable_videos()`. A denied private video is a **404**, never a 403.
3. **No mass assignment:** request schemas never contain `role`, `owner`/`channel_id`, `status`, `is_hidden` or counters.
4. **Object storage:** keys are built only from server ids (`storage/keys.py`), never from user filenames. Video bytes never go into PostgreSQL. No MinIO URL is ever returned to the client.
5. **Counters** (`view_count`, `like_count`, …) change with atomic `UPDATE … SET n = n + :d` in the **same transaction** as the row they count.
6. **Celery tasks are enqueued after the DB commit** and must be idempotent (claim with a conditional `UPDATE … WHERE status = …`).
7. Errors are raised as `core.errors.AppError` subclasses and rendered as the `{"error": {code, message, details}}` envelope.
8. Endpoints are sync `def` (thread pool). Do not mix in async DB access.

## Code conventions

- Typed everywhere: SQLAlchemy `Mapped[...]` / `mapped_column`, Pydantic v2 models, and return types on public functions.
- Ruff is the linter and formatter (config in `backend/pyproject.toml`, line length 100). Keep imports sorted.
- Use `logging.getLogger(__name__)`, never `print`. Never log passwords, tokens or full media URLs.
- Settings only via `core.config.get_settings()`. No `os.environ` reads scattered in code.
- Every schema change ships as a reviewed Alembic migration. Constraint names follow the naming convention in `db/base.py`.

## Security non-negotiables

- Every permission is checked in the backend. The frontend only hides things.
- Passwords: Argon2id only. Tokens: access JWT in memory, refresh token as an HttpOnly cookie, stored hashed in the DB.
- Validate all input with Pydantic constraints. Uploads are checked by size, type, magic bytes and ffprobe.
- ffmpeg/ffprobe always run with `-protocol_whitelist file`, a timeout and list-form arguments (no shell).
- Never commit `.env` or secrets. Never weaken a check to make a test pass.

## Testing rules

- Each feature ships with tests for its acceptance criteria in `docs/architecture.md § 1.3`, **including negative authorization cases** (401/403/404).
- Tests run against real PostgreSQL / Redis / MinIO (dev compose). Do not mock the database or storage for integration tests.
- **Never report a test result that was not actually run in this session.** Quote the real pytest summary line.
- A failing test is fixed or reported, never skipped or deleted silently.

## Definition of done (per task)

1. Implemented without TODOs in critical paths and without fake or placeholder responses.
2. `ruff check` + `ruff format --check` clean, and the full test suite green (real output shown).
3. Diff reviewed by the `code-reviewer` agent, and by `security-reviewer` if it touches auth, access, uploads, media or admin. Findings fixed or explicitly deferred with a reason.
4. Docs updated if behaviour or design changed.
5. Committed as a small Conventional Commit.

## Git

- Conventional Commits with scope: `feat(backend): …`, `test(backend): …`, `build(infra): …`, `docs: …`, `chore(ai): …`.
- One branch per stage (`stage/<n>-<name>`), merged into `main` with `--no-ff` after the architect approves, then tagged `stage-<n>`.
- End commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Never push without the architect's explicit OK. Never force-push, rewrite history or squash the project into one commit.**

## AI artifacts (part of the submission)

- `ai/prompts/` holds the prompts given to Claude, extracted verbatim from the session transcripts.
- At the end, the raw `*.jsonl` session files from `~/.claude/projects/c--Users-LOQ-Desktop-youtube-clone/` are copied unmodified into `ai/sessions/`.
- `.claude/` (settings, agents, skills, hooks) and this file are submitted as-is.
