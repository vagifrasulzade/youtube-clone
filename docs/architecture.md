# Architecture

> **Status: Approved — Stage 1, 2026-11-14.** Implementation in progress; each section is updated as its stage lands.

Related documents: [database.md](database.md) · [api.md](api.md) · [video-storage.md](video-storage.md) · [security.md](security.md) · [plan.md](plan.md)

---

## 1. Requirements breakdown

### 1.1 Screens → capabilities

| Screen | What the user sees (YouTube parity) | Backend capability behind it |
|---|---|---|
| **Home** | Header (logo, search with suggestions, *Create*, avatar menu), collapsible sidebar (full 240 px / mini 72 px / drawer on mobile), responsive thumbnail grid with duration badge, "1.2M views • 3 days ago", skeletons | Public feed (keyset pagination), thumbnail delivery |
| **Watch** | Player with seeking, title, channel row + Subscribe, like/dislike pill, Share, Save-to-playlist, collapsible description, comments + replies, related videos column | Visibility policy, Range streaming, reactions, comments, views, related query |
| **Channel** | Banner, avatar, name, @handle, subscribers, video count, tabs *Videos / Playlists / About*, Subscribe | Channel profile, channel video & playlist lists, subscriptions |
| **Search** | Result rows (large thumbnail left, metadata right), sort, pagination | PostgreSQL full-text + trigram search, suggestions |
| **Upload** | YouTube-Studio-style dialog: drop zone → upload starts immediately with progress → details (title, description, thumbnail choice) → visibility → processing status | Draft creation, presigned POST to MinIO, upload-complete, Celery processing with progress |
| **Login / Register** | Forms with validation, logout from avatar menu | Argon2id, JWT access + rotating refresh token |
| **Studio** | Table of my videos in all states (draft, processing, failed, hidden), edit metadata, delete, share private video, playlists | Owner-scoped CRUD, video permissions |
| **Moderation** | Report queue, report detail with video preview, hide/restore, audit log | Reports, moderation actions, RBAC |
| **Admin** | Stats, user management (role, ban), video management | Admin APIs, self/last-admin protection |

Cheap additions with a big effect on looking like YouTube: History, Liked videos, Subscriptions feed, subscriptions list in the sidebar, 11-character video ids (`/watch?v=dQw4w9WgXcQ` style), Roboto font, YouTube's spacing and breakpoints.

### 1.2 Non-functional requirements

- **Video is the heart.** Video bytes never go into PostgreSQL and, in production mode, never pass through Python. Uploads go browser → MinIO and playback goes MinIO → nginx → browser.
- **Authorization lives in the backend only.** The UI hides buttons for UX; every rule is enforced server-side.
- **One-command deploy** on clean Ubuntu (`./deploy.sh`), including demo data.
- **Reproducible:** pinned dependencies and image tags, Alembic migrations, idempotent seed.
- **Testable:** critical behaviour covered by automated tests running against real PostgreSQL, Redis, MinIO and ffmpeg (no SQLite or mocks for the storage path).

### 1.3 Our definition of "works correctly"

These acceptance criteria are our own contract. Each one maps to at least one automated test or to the post-deploy smoke test ([plan.md § Testing](plan.md#2-testing-strategy)).

**A. Upload & processing**
- **A1** A valid video (mp4 / mov / webm / mkv / avi, up to `MAX_UPLOAD_BYTES`, default 2 GiB) uploads with real byte progress and ends `ready` with duration, resolution and a thumbnail.
- **A2** A file larger than the limit is rejected **by the storage upload policy**, not only by the UI.
- **A3** A non-video renamed to `.mp4` ends `failed` with a readable reason. Nothing playable is published.
- **A4** A video does not appear in the feed, search or channel page until it is `ready`.
- **A5** Abandoned uploads leave no orphans: raw objects expire and stale draft rows are removed.
- **A6** Processing the same video twice (e.g. a redelivered task) is harmless.

**B. Playback**
- **B1** A `Range: bytes=…` request returns `206 Partial Content` with a correct `Content-Range`, and seeking works in Chrome and Firefox.
- **B2** Storage is never directly reachable. No API response contains a MinIO URL, and the buckets are not anonymously readable.

**C. Visibility**
- **C1** Public: everyone. Unlisted: anyone with the link, but never listed. Private: the owner plus explicitly granted users (moderators and admins too, to review reports).
- **C2** An unauthorized viewer gets `404` (not `403`) for the private video's metadata, stream, thumbnail, comments, reactions and reports, so its existence is not revealed.
- **C3** Private and unlisted videos never appear in home, search, suggestions, related or channel lists. Inside a playlist they appear as "Private video" to viewers without access.
- **C4** Revoking access takes effect on the next request, including the next Range request of a player that is already open.
- **C5** A video hidden by moderation behaves as "owner + staff only".

**D. Interactions**
- **D1** One reaction per user per video. Switching like ↔ dislike adjusts both counters atomically, and counters always equal the row counts (asserted by tests).
- **D2** Comments and replies: the author, the video owner, moderators and admins can delete a comment. Everyone else gets `403`.
- **D3** Subscribing is idempotent and you cannot subscribe to your own channel. The subscriber count matches the rows.
- **D4** At most one counted view per viewer per video per 24 hours.

**E. Auth & roles**
- **E1** Passwords are stored only as Argon2id hashes. A login error does not reveal whether the email exists.
- **E2** Refresh tokens rotate, and reusing an old refresh token revokes the whole session family.
- **E3** A banned user loses access on their next request, not when their token expires.
- **E4** Users cannot escalate their role, moderators cannot manage users, admins cannot demote or ban themselves, and the last admin cannot be removed.
- **E5** Login brute force is rate-limited (`429` + `Retry-After`).

**F. Deploy**
- **F1** On clean Ubuntu 22.04 / 24.04, `./deploy.sh` produces the app at `http://<host>/`, Swagger at `/docs` and the demo data. `scripts/smoke_test.sh` then passes: register → login → upload → process → watch (206) → like → comment.

---

## 2. System architecture

### 2.1 Overview

```
                    ┌────────────────────────────────────────┐
                    │  Browser — React SPA (static build)    │
                    └───────────────────┬────────────────────┘
                                        │ HTTP :80  (the only published port)
┌───────────────────────────────────────▼──────────────────────────────────────┐
│ nginx                                                                        │
│   /                    → SPA files (index.html fallback)                     │
│   /api/*  /docs        → api:8000                                            │
│   /storage/upload      → minio:9000/yt-uploads  (POST only, policy-checked)  │
│   /_media/*  internal  → minio:9000             (only via X-Accel-Redirect)  │
└──────────────┬──────────────────────────────────────────────┬────────────────┘
               │                                              │
      ┌────────▼────────┐   presign · HEAD · delete    ┌──────▼─────────┐
      │ api  (FastAPI)  ├─────────────────────────────▶│ MinIO          │
      └───┬─────────┬───┘                              │  yt-uploads    │
      SQL │         │ enqueue · rate limits            │  yt-media      │
   ┌──────▼─────┐ ┌─▼─────────┐   tasks   ┌──────────┐ └──────▲─────────┘
   │ PostgreSQL │ │ Redis     ├──────────▶│ worker   ├────────┘ get / put
   └──────▲─────┘ └───────────┘           │ Celery + │
          │                               │ ffmpeg   │
          └──────── status · metadata ────┴──────────┘
                    beat: periodic cleanup + stuck-job watchdog
```

### 2.2 Services (docker-compose)

| Service | Image | Responsibility | Published |
|---|---|---|---|
| `nginx` | built from `infra/nginx` (multi-stage: Node build of the SPA → nginx alpine) | SPA, reverse proxy, upload pass-through, protected media delivery, security headers, coarse rate limit | **:80** |
| `api` | `backend/Dockerfile` (python:3.13-slim) | REST API, auth, authorization, presigning | internal |
| `worker` | same image, `celery worker` | probe, transcode/remux, thumbnails, object deletion | internal |
| `beat` | same image, `celery beat` | schedules cleanup of stale drafts and the stuck-job watchdog | internal |
| `migrate` | same image, one-shot `alembic upgrade head` | schema migrations before the api starts | — |
| `postgres` | postgres:17-alpine | system of record | internal |
| `redis` | redis:7-alpine | Celery broker, rate-limit counters, view dedupe, processing progress | internal |
| `minio` | `cgr.dev/chainguard/minio` pinned by digest (MinIO built from upstream source; upstream stopped publishing community images) | object storage | internal |
| `minio-init` | `cgr.dev/chainguard/minio-client`, one-shot | buckets, lifecycle rule, least-privilege app user | — |

The containers share one backend image, so the api and worker always run the same models and code.

### 2.3 Key decisions

| # | Decision | Why | Trade-off accepted |
|---|---|---|---|
| D1 | **Modular monolith** (FastAPI app with routers → services → models), not microservices | 10 days, one team. The module boundaries give the same separation without network seams | Scaling is per process, not per feature |
| D2 | **Sync SQLAlchemy 2.0 + psycopg 3**, with endpoints running in FastAPI's thread pool | API and Celery share the same models and session code. Heavy I/O (video bytes) bypasses Python, so async would gain little | Concurrency is bounded by thread pool size (fine at this scale) |
| D3 | **Browser uploads straight to MinIO using a presigned POST policy** (proxied by nginx on the same origin) | Bytes skip the API. The policy is enforced *by MinIO*: exact key, size range and content type. The same origin means no CORS | No resumable uploads (would need multipart presign) |
| D4 | **Playback via nginx `X-Accel-Redirect`**: FastAPI authorizes each request, then nginx streams from MinIO with native Range support | Per-request authorization without Python moving bytes. Seeking, 206 responses and keep-alive are handled by nginx and MinIO | Needs a fallback for dev/tests → `MEDIA_DELIVERY=proxy` streams through FastAPI |
| D5 | **Progressive MP4** (H.264/AAC, `+faststart`) + HTTP Range, **not HLS** | One URL per video makes authorization simple, whereas HLS has hundreds of segments to authorize. The requirement allows Range or HLS | No adaptive bitrate: a single 720p rendition |
| D6 | **Two buckets**: `yt-uploads` (raw, browser write-only, auto-expiring) and `yt-media` (processed, never public) | A clear trust boundary: untrusted bytes never live next to served bytes, and a lifecycle rule cleans abandoned uploads for free | Two buckets to provision (done by `minio-init`) |
| D7 | **Celery + Redis** for processing. Redis also handles rate limiting and view dedupe | Standard, required by the brief, retries and time limits built in. Redis data is ephemeral by design | Redis is a dependency of the API (it fails open for view dedupe and closed for rate limits on auth) |
| D8 | **Denormalized counters** (views, likes, dislikes, comments, subscribers), updated with atomic `UPDATE … SET n = n + 1` **in the same transaction** as the row change | The feed and watch page need counts without `COUNT(*)` on hot paths | Must be kept honest, so tests assert counter == row count |
| D9 | **PostgreSQL FTS (`simple` config) + `pg_trgm`** | `simple` works for any language (AZ/RU/EN titles), which English stemming would not. Trigram gives partial and typo-tolerant title matches and powers suggestions | Not as smart as a dedicated search engine; good enough for "search by title" |
| D10 | **Access token in memory + refresh token in an HttpOnly cookie**. `<video>` and `<img>` URLs carry a **short-lived signed media token** | XSS cannot read the refresh token. Media elements cannot send `Authorization` headers, so URLs are self-authorizing but still re-checked against the DB | Tokens appear in media URLs, so nginx access logs strip query strings on `/api/v1/media/` |
| D11 | **11-char random video ids** (`[A-Za-z0-9_-]{11}`), UUIDs everywhere else | YouTube-identical URLs, non-enumerable | Two id formats in the codebase |
| D12 | **nginx also serves the SPA**, with one public port and the same origin for API, uploads and media | No CORS, cookies work with `SameSite=Strict`, a simple firewall | — |

### 2.4 Backend layering

```
api/v1/<router>.py   HTTP only: parse/validate (Pydantic), call a service, map to response schema
        │
services/<domain>.py business rules, transactions, counters, audit entries
        │   └── services/access.py  ← the ONLY place that decides "can this viewer see this video"
        │
models/              SQLAlchemy 2.0 typed models (Mapped[...])
storage/             S3 adapter (boto3): presign POST/GET, head, delete-prefix; key builders
workers/             Celery app, tasks, ffmpeg/ffprobe wrappers
core/                settings, security (Argon2, JWT), error envelope, logging, rate limiter
```

Rules (also written into `CLAUDE.md`):
- Routers never build authorization logic or run ad-hoc queries; they call services.
- Every query that lists videos goes through `access.listable_videos()`, and every single-video read goes through `access.get_viewable_video_or_404()`.
- Request/response schemas are separate from models. Create/Update schemas never contain `role`, `owner`, `status` or counters, which prevents mass assignment.
- Object keys are built only from server-side ids, never from user filenames.

### 2.5 Frontend architecture

- React 19 + TypeScript + Vite + Tailwind v4 (already in the repo), React Router, TanStack Query, Axios.
- **API types are generated from `/openapi.json`** (`openapi-typescript`), so the frontend/backend contract cannot drift silently.
- `AuthProvider` keeps the access token in memory and silently refreshes on load. An Axios interceptor handles 401 with a single-flight refresh and retries once.
- Route guards `RequireAuth` and `RequireRole` exist for UX only; the backend still enforces everything.
- Every data view has loading (skeleton), error (retry) and empty states.
- Layout matches YouTube's desktop metrics: a 56 px header, a 240 px sidebar / 72 px mini sidebar, a 1–6 column grid by breakpoint, a 16:9 thumbnail with 12 px radius, and self-hosted Roboto.

### 2.6 Operations

- **Health:** `/api/v1/health/live` (process) and `/api/v1/health/ready` (DB, Redis, MinIO). Docker health checks gate `depends_on`.
- **Startup order:** postgres / redis / minio healthy → `minio-init` + `migrate` complete → `api`, `worker`, `beat` → `nginx`.
- **Logs:** JSON to stdout with a request id (`X-Request-ID`, generated by nginx and propagated to logs and Celery tasks).
- **Periodic jobs (beat):** delete `awaiting_upload` drafts older than 24 h; re-enqueue `queued` videos stuck for more than 10 min; mark `processing` jobs older than the hard time limit as `failed`.
- **Backups:** `scripts/backup.sh` runs `pg_dump` plus `mc mirror` of `yt-media`.
- **Config:** a single `.env` (generated by `deploy.sh` with random secrets). The app refuses to start in production with default secrets.

---

## 3. Project structure

```
youtube-clone/
├── CLAUDE.md                      # rules for the AI agent: stack, layering, definition of done, git
├── .claude/
│   ├── settings.json              # permission allow/deny lists, hooks
│   ├── agents/                    # code-reviewer, security-reviewer, test-engineer
│   └── skills/                    # stage, verify, commit workflows
├── ai/
│   ├── prompts/                   # prompts used, verbatim
│   └── sessions/                  # Claude Code *.jsonl transcripts (copied at the end)
├── README.md
├── deploy.sh                      # one-command deploy on clean Ubuntu
├── docker-compose.yml
├── docker-compose.dev.yml         # dev overrides: published ports, reload, MEDIA_DELIVERY=proxy
├── .env.example
├── .github/workflows/ci.yml       # ruff, pytest (with services), tsc, eslint, build
├── backend/
│   ├── Dockerfile                 # python:3.13-slim + ffmpeg; api/worker/beat/migrate share it
│   ├── pyproject.toml             # ruff, pytest, mypy config
│   ├── requirements.txt           # pinned runtime deps
│   ├── requirements-dev.txt
│   ├── alembic.ini
│   ├── alembic/{env.py, versions/}
│   ├── app/
│   │   ├── main.py                # app factory: routers, middleware, exception handlers
│   │   ├── core/                  # config, security, errors, logging, rate_limit
│   │   ├── db/                    # declarative base (naming convention), session
│   │   ├── models/                # user, channel, video, comment, reaction, subscription,
│   │   │                          # playlist, view, report, moderation, auth (refresh tokens)
│   │   ├── schemas/               # Pydantic DTOs per domain
│   │   ├── api/
│   │   │   ├── deps.py            # db, current_user, optional_user, require_role
│   │   │   └── v1/                # auth, videos, media, comments, channels, playlists,
│   │   │                          # search, me, studio, moderation, admin, health
│   │   ├── services/              # business logic; access.py = visibility policy
│   │   ├── storage/               # s3 client wrapper, object key builders
│   │   ├── workers/
│   │   │   ├── celery_app.py
│   │   │   ├── ffmpeg.py          # probe/transcode/thumbnail with whitelists and timeouts
│   │   │   └── tasks/             # process_video, delete_objects, cleanup, watchdog
│   │   └── cli/                   # seed, create_admin
│   └── tests/
│       ├── conftest.py            # app client, DB savepoint per test, redis, minio, users
│       ├── factories.py
│       ├── unit/                  # security utils, access matrix, ffmpeg arg building
│       └── integration/           # one module per feature (auth, uploads, streaming, …)
├── frontend/
│   └── src/
│       ├── api/                   # axios client + interceptors, endpoint modules, schema.d.ts
│       ├── auth/                  # AuthProvider, RequireAuth, RequireRole
│       ├── components/            # layout/, video/, comments/, channel/, ui/
│       ├── pages/                 # Home, Watch, Channel, Search, Login, Register, Studio,
│       │                          # Upload dialog, Playlist, History, Liked, Moderation, Admin
│       ├── hooks/
│       └── lib/                   # formatters: "1.2M views", "3 days ago", "12:34"
├── infra/
│   ├── nginx/                     # Dockerfile, nginx.conf, security headers
│   └── minio/init.sh              # buckets, lifecycle, app user + policy
├── scripts/
│   ├── smoke_test.sh              # register → login → upload → process → watch → like → comment
│   ├── test.sh                    # run backend tests inside Docker
│   └── backup.sh
└── docs/
    ├── architecture.md · database.md · api.md · video-storage.md · security.md
    ├── deployment.md · testing.md · ai-workflow.md   (written in later stages)
    └── plan.md
```
