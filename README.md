# YouTube Clone

A YouTube-like video platform built as a 10-day technical assessment with AI-assisted development (Claude Code).

**Stack:** FastAPI · PostgreSQL 17 · SQLAlchemy 2 · Alembic · Redis · Celery · MinIO (S3) · ffmpeg · nginx · React + TypeScript + Vite + Tailwind · Docker Compose.

## Quick start (clean Ubuntu 22.04 / 24.04)

```bash
git clone https://github.com/vagifrasulzade/youtube-clone.git
cd youtube-clone
./deploy.sh
```

`deploy.sh` installs Docker if missing, generates `.env` with random secrets, builds and starts every service, loads demo data and checks health. Then open:

| | |
|---|---|
| App | `http://<server-ip>/` |
| Swagger UI | `http://<server-ip>/docs` |
| Health | `http://<server-ip>/api/v1/health/ready` |

**Demo accounts** (password `demo-password-123`): `admin@example.com` (admin), `moderator@example.com` (moderator), `alice@example.com`, `bob@example.com`, `carol@example.com` (creators), `viewer@example.com` (viewer).

After deployment, `scripts/smoke_test.sh` runs the scenario *register → login → upload → process → watch → like → comment* through nginx.

## What works

| Area | Status |
|---|---|
| Accounts: register, login, logout, refresh-token rotation, roles (user / moderator / admin), bans | ✅ |
| Upload: private draft + presigned POST straight to MinIO (size/type/key enforced by storage), magic-byte check | ✅ |
| Streaming with HTTP Range (seek), per-request authorization, media served by nginx via X-Accel-Redirect | ✅ |
| Private videos shared with chosen users; unlisted; hidden by moderation | ✅ |
| Likes/dislikes, subscriptions, view counts (24 h dedupe), history, liked videos | ✅ |
| Feeds (home, channel, subscriptions, related), search (full-text + typo-tolerant) with suggestions | ✅ |
| Playlists, Creator Studio list, channel profile and images | ✅ |
| Reports, moderation (hide/restore, resolve/dismiss) with an audit log; admin dashboard API | ✅ |
| Housekeeping: stale-draft cleanup, stuck-job watchdog, storage cleanup on delete (Celery beat) | ✅ |
| **Video processing worker** (ffprobe validation, remux/transcode, thumbnails) | ⏳ ffmpeg wrapper done; the Celery task is not written yet, so newly uploaded videos stay `queued` |
| **Comments API** | ⏳ table and seed data exist; endpoints not written yet |
| **Frontend (YouTube-style UI)** | ⏳ next stage |

## Documentation

- [Architecture](docs/architecture.md): requirements, our acceptance criteria (A1–F1), components, key decisions
- [Database](docs/database.md): ER diagram, tables, constraints, indexes, what is stored where
- [API](docs/api.md): every endpoint (live contract: `/docs`)
- [Video storage](docs/video-storage.md): upload, processing and protected delivery
- [Security](docs/security.md): threat model, auth, access policy, rate limits, hardening
- [Plan](docs/plan.md): roadmap, testing strategy, git workflow, AI workflow

## Development

```bash
cp .env.example .env            # fill in the change-me values (or run deploy.sh once)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio minio-init
cd backend
python -m venv venv && venv/bin/pip install -r requirements-dev.txt   # Windows: venv\Scripts\
cp .env.example .env            # then set DATABASE_URL / S3 keys to match ../.env
venv/bin/python -m pytest       # ~320 tests against real PostgreSQL, Redis and MinIO
venv/bin/python -m ruff check . && venv/bin/python -m ruff format --check .
```

`scripts/test.sh` runs the whole suite in a clean container (isolated compose project).

## Repository layout

```
backend/      FastAPI app (api → services → models), Alembic migrations, tests
frontend/     React SPA
infra/        nginx (SPA + reverse proxy + X-Accel media), MinIO provisioning
scripts/      test runner, smoke test
docs/         design documentation
ai/           prompts given to the AI (verbatim) and the raw session transcripts
CLAUDE.md, .claude/   AI agent rules, subagents, skills, hooks, settings
deploy.sh     one-command deployment
```

## AI-assisted development

Built with Claude Code acting as implementer while the developer acted as architect and reviewer. `CLAUDE.md` holds the project rules (layering, the single access policy, definition of done). `.claude/` holds the review subagents, the workflow skills and a lint hook. Every stage was planned, implemented with tests and reviewed (including a security review whose findings were fixed in `d36fc19`), then merged with `--no-ff` and tagged `stage-N`. The prompts are in `ai/prompts/`, and the raw session transcripts are added to `ai/sessions/`.
