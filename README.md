# YouTube Clone

A YouTube-like video platform built as a 10-day technical assessment with AI-assisted development (Claude Code).

**Stack:** FastAPI · PostgreSQL 17 · SQLAlchemy 2 · Alembic · Redis · Celery · MinIO (S3) · ffmpeg · nginx · React 19 + TypeScript + Vite + Tailwind · Docker Compose.

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

After deployment, `scripts/smoke_test.sh` runs *register → login → upload → process → watch (HTTP 206) → like → comment* through nginx, and checks that a copied media link without the viewer's cookie is refused (404).

## Accounts and roles

**Demo accounts:**

- `admin@example.com` (admin)
- `moderator@example.com` (moderator)
- `alice@example.com`, `bob@example.com`, `carol@example.com` (creators)
- `viewer@example.com` (viewer)

The demo password is **generated randomly** by `deploy.sh`. It is printed at the end of the run and stored in `.env` as `DEMO_PASSWORD`. For local development without `deploy.sh` it defaults to `demo-password-123`.

Anyone can register at `/register` (email, password of 8+ characters, channel name and a handle such as `alice`; a leading `@` is accepted). New accounts get the `user` role.

**Admins are never created through the web API**, so a stolen session cannot mint new admins. Promote an existing account from the server shell:

```bash
docker compose exec api python -m app.cli.create_admin someone@example.com
```

Admins can then make other users moderators in the admin panel.

**Forgot a password?** This includes the demo accounts after `DEMO_PASSWORD` was changed in `.env`: the seed stores the password only once, so editing `.env` later does not change it. Set a new password from the server shell:

```bash
docker compose exec api python -m app.cli.reset_password admin@example.com
```

It asks for the new password twice without echo (never as an argument, so it stays out of the shell history) and signs that account out everywhere. Every permission is checked by the API: the frontend only hides links a role cannot use.

## Screens

| Screen | URL | Who |
| --- | --- | --- |
| Home feed (infinite scroll) | `/` | everyone |
| Watch: player with seeking, like/dislike, subscribe, comments and replies, save to playlist, report, related videos | `/watch?v=<id>` | everyone (private: owner and invited users) |
| Search with suggestions, sort and pages | `/results?search_query=…` | everyone |
| Channel (videos / playlists tabs) | `/@<handle>` | everyone |
| Playlist | `/playlist?list=<id>` | everyone (private: owner) |
| Sign in / create account | `/login`, `/register` | guests |
| Upload: drag & drop, progress, processing status | `/upload` | signed in |
| Studio: all my videos in every state | `/studio` | signed in |
| Studio video details: edit, thumbnails, share private video, delete | `/studio/video/<id>` | owner |
| Library: subscriptions feed, history, liked, shared with me, playlists | `/feed/subscriptions`, `/feed/history`, `/playlist/liked`, `/feed/shared`, `/playlists` | signed in |
| Moderation: report queue, hide/restore, audit log | `/moderation` | moderator, admin |
| Admin: stats, users (role, ban), all videos | `/admin` | admin |

## What works

| Area | Status |
|---|---|
| Accounts: register, login, logout, refresh-token rotation, roles (user / moderator / admin), bans | ✅ |
| Upload: private draft + presigned POST straight to MinIO (size/type/key enforced by storage), magic-byte check | ✅ |
| Video processing worker: ffprobe validation, remux or transcode to H.264 720p, 3 thumbnails, retries, output caps | ✅ |
| Streaming with HTTP Range (seek), per-request authorization, media served by nginx via X-Accel-Redirect | ✅ |
| Private videos shared with chosen users; unlisted; hidden by moderation | ✅ |
| Likes/dislikes, subscriptions, view counts (24 h dedupe), history, liked videos | ✅ |
| Comments with one level of replies (author / video owner / staff can delete; staff deletions audited) | ✅ |
| Feeds (home, channel, subscriptions, related), search (full-text + typo-tolerant) with suggestions | ✅ |
| Playlists, Creator Studio, channel profile and images | ✅ |
| Reports, moderation (hide/restore, resolve/dismiss) with an audit log; admin dashboard | ✅ |
| Housekeeping: stale-draft cleanup, stuck-job watchdog, storage cleanup on delete (Celery beat) | ✅ |
| Frontend for every screen above (YouTube-style layout, full/mini sidebar, mobile drawer) | ✅ |

**Tests:**

- Backend: 407, run against real PostgreSQL, Redis and MinIO, and against real ffmpeg for the processing tests.
- Frontend: 38 Vitest tests.
- CI runs both suites, lint and the production build.

Which test covers which acceptance criterion is in [docs/testing.md](docs/testing.md).

## Documentation

- [Architecture](docs/architecture.md): requirements, our acceptance criteria (A1–F1), components, key decisions
- [Database](docs/database.md): ER diagram, tables, constraints, indexes, what is stored where
- [API](docs/api.md): every endpoint (live contract: `/docs`)
- [Video storage](docs/video-storage.md): upload, processing and protected delivery
- [Security](docs/security.md): threat model, auth, access policy, rate limits, hardening
- [Plan](docs/plan.md): roadmap, progress, deviations from the design, testing strategy, git workflow
- [Deployment](docs/deployment.md): prerequisites, what deploy.sh does, configuration, operations, troubleshooting
- [Testing](docs/testing.md): how to run the suites, acceptance criteria mapped to tests
- [AI workflow](docs/ai-workflow.md): agent setup, working loop, verification, reviews, what did not go to plan

## Development

Backend (dev infrastructure on localhost: PostgreSQL `:5433`, Redis `:6380`, MinIO `:9000`/`:9001`):

```bash
cp .env.example .env            # fill in the change-me values (or run deploy.sh once)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis minio minio-init
cd backend
python -m venv venv && venv/bin/pip install -r requirements-dev.txt   # Windows: venv\Scripts\
cp .env.example .env            # then set DATABASE_URL / S3 keys to match ../.env
venv/bin/python -m pytest       # the ffmpeg tests are skipped (with a reason) if ffmpeg is not installed
venv/bin/python -m ruff check . && venv/bin/python -m ruff format --check .
```

`scripts/test.sh` runs the **whole** backend suite in a clean Python 3.13 + ffmpeg container, as a separate compose project on its own network. It can run while the main stack is up.

Frontend:

```bash
cd frontend
npm ci
npm test            # Vitest
npm run lint
npm run build       # type-check + production build
```

To try a frontend change in the browser, rebuild the stack (`docker compose up -d --build`). nginx serves the built SPA and proxies the API at `http://127.0.0.1/`.

## Repository layout

```
backend/      FastAPI app (api → services → models), Celery worker, Alembic migrations, tests
frontend/     React SPA (pages, components, auth/session handling, generated API types)
infra/        nginx (SPA + reverse proxy + X-Accel media), MinIO provisioning
scripts/      Docker test runner, end-to-end smoke test, prompt extraction, submission packager
docs/         design documentation
ai/           prompts given to the AI (verbatim) and the raw session transcripts
CLAUDE.md, .claude/   AI agent rules, subagents, skills, hooks, settings
deploy.sh     one-command deployment
```

## AI-assisted development

The project was built with Claude Code as the implementer, while the developer acted as architect and reviewer.

- `CLAUDE.md` holds the project rules: layering, the single access policy and the definition of done.
- `.claude/` holds the review subagents, the workflow skills and a lint hook.
- Every stage was planned, implemented with tests, and reviewed by a code-review agent and a security-review agent before it was committed. Their findings were fixed in follow-up commits (for example `d36fc19` for auth and `b650f3b`…`660691c` for stages 5–10), or deferred with the reason recorded in the docs.

The prompts are in `ai/prompts/`. `python scripts/package_submission.py` copies the raw session transcripts into `ai/sessions/` and builds the submission zip, including `.git`.
