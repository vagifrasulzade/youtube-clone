# Security design

> **Status: Approved — Stage 1, 2026-11-14.** Principle: **every permission is enforced in the backend**. The frontend only hides what the user cannot do.

## 1. Assets and threats

| Asset | Main threats | Primary controls |
|---|---|---|
| Accounts | Credential stuffing, brute force, token theft | Argon2id, rate limits, short-lived JWTs, rotating refresh tokens with reuse detection |
| Private videos | IDOR, URL sharing or guessing, leaked storage URLs | One access policy, `404` on deny, non-enumerable ids, no public storage URLs, re-check on every media request |
| Admin/moderation functions | Privilege escalation, mass assignment | Role checks against DB state, no role field in user-facing schemas, self/last-admin protection, audit log |
| Storage & workers | Oversized or malicious uploads, ffmpeg exploits, SSRF via media | POST policy limits, magic bytes + ffprobe allowlist, ffmpeg protocol whitelist, resource limits, isolated worker |
| Service availability | Abuse of expensive endpoints | Redis rate limits, nginx `limit_req`, upload quotas per hour |

## 2. Authentication

| Item | Design |
|---|---|
| Password hashing | **Argon2id** (`argon2-cffi`, RFC 9106 parameters: t=3, m=64 MiB, p=4). Rehash on login if the parameters change. Lighter parameters are allowed only in tests |
| Password policy | 8–128 characters (the upper bound prevents hashing DoS), and the password may not equal the email or handle |
| Login | Generic `invalid_credentials` error. When the user does not exist, a dummy hash is still verified, so timing does not reveal accounts |
| Access token | JWT HS256 (PyJWT), 15 min, claims `sub`, `typ=access`, `iat`, `exp`, `jti`, `iss`. The algorithm is pinned on decode |
| Per-request user load | Every authenticated request loads the user from the DB (one PK lookup). **Role and ban status come from the DB, not the token**, so a role change or ban applies immediately (E3) |
| Refresh token | 256-bit random opaque value, stored as SHA-256 only, 30 days, **rotated on every use**, and a login (family) lives at most 90 days. Presenting an already-rotated token revokes the whole family (E2). Exception: within 10 s of its rotation it gets `401 refresh_superseded` without revocation, so two tabs refreshing at once do not log the user out. Revocation locks the family's rows before updating them, so a token minted by a concurrent rotation is revoked too |
| Refresh cookie | `HttpOnly`, `SameSite=Strict`, `Path=/api/v1/auth`, and `Secure` when served over HTTPS (`COOKIE_SECURE`). The cookie endpoints also check `Origin` |
| Frontend storage | Access token in memory only (never in `localStorage`). Silent refresh on page load |
| Media token | A separate secret, `typ=media`, scoped to one video, 4 h. It identifies the viewer but grants nothing on its own (see § 4) |

## 3. Authorization

### 3.1 Role / action matrix

| Action | Guest | User | Owner | Moderator | Admin |
|---|:-:|:-:|:-:|:-:|:-:|
| Watch public / unlisted (ready, not hidden) | ✓ | ✓ | ✓ | ✓ | ✓ |
| Watch private | – | if granted | ✓ | ✓ | ✓ |
| Watch hidden | – | – | ✓ (with notice) | ✓ | ✓ |
| Upload | – | ✓ | | | |
| Edit metadata / visibility / grants | – | – | ✓ | – | – |
| Delete video | – | – | ✓ | – (hides instead) | ✓ |
| Like, comment, report (requires view access) | – | ✓ | ✓ | ✓ | ✓ |
| Delete comment | – | own | own + any on own video | any | any |
| Report queue, hide / restore, audit log | – | – | – | ✓ | ✓ |
| Stats, users, roles, ban / unban | – | – | – | – | ✓ |

Admin guardrails: an admin cannot change their own role or ban themselves, cannot ban another admin without demoting them first, and the last admin can never be demoted. Admins are created only through the seed or the `create_admin` CLI, never through the public API.

### 3.2 The video access policy (single source of truth)

```python
def can_view(video, viewer) -> bool:
    if viewer and viewer.id == video.owner_id:
        return True                         # owner always (even hidden / processing)
    if viewer and viewer.role_level >= MODERATOR:
        return True                         # staff can review any video
    if video.is_hidden or video.status != "ready":
        return False
    if video.visibility in ("public", "unlisted"):
        return True
    return viewer is not None and has_grant(video.id, viewer.id)   # private
```

- Every single-video endpoint (detail, stream, thumbnail, comments, reactions, views, reports, related, playlist add) calls `get_viewable_video_or_404`. **A denial is a `404`**, so a private video's existence is not revealed (C2).
- Every list query (feed, search, suggestions, related, channel page) composes `listable_videos()` = `public AND ready AND NOT hidden`. Unlisted and private videos are never listed (C3).
- Management endpoints (PATCH, DELETE, grants) on a video the caller *can* see but does not own return `403`. On one they cannot see, they return `404`.
- Tests: a table-driven test covers *visibility × status × hidden × viewer type* against the policy, plus endpoint-level tests confirming each route actually uses it.

## 4. Object storage and media

- Both buckets are private, with no anonymous access. The application uses a least-privilege MinIO user limited to the two buckets. MinIO is not published on any host port.
- **No storage URL ever reaches the browser.** Uploads go through a same-origin path with a signed policy, and downloads use `X-Accel-Redirect` to an `internal` nginx location with a presigned URL valid for 60 s.
- Every media request (including each Range request) re-checks `can_view` in the DB, so revoking a grant or hiding a video stops playback at the next request.
- Media tokens appear in URLs, so the nginx access log for `/api/v1/media/` omits query strings, and `Referrer-Policy: strict-origin-when-cross-origin` applies.
- Responses send `X-Content-Type-Options: nosniff` and `Content-Disposition: inline`. Private media sends `Cache-Control: private, no-store`.

## 5. Input validation

- All request bodies go through Pydantic v2 models with length, range and pattern constraints. Text is normalized (trimmed, control characters rejected).
- **Mass assignment:** Create/Update schemas are separate from models and never include `role`, `owner`, `status`, `is_hidden` or counters.
- Database access goes only through the SQLAlchemy ORM / Core with bound parameters. No string-built SQL.
- Comments and descriptions are plain text. React escapes them; there is no `dangerouslySetInnerHTML`. Links in descriptions are linkified with `http(s)` only.
- Images (thumbnails, avatars, banners) are size-limited and checked against an allowlist, then **decoded and re-encoded** with Pillow to JPEG. This strips metadata and defeats polyglot files.

## 6. Media processing hardening

ffmpeg parses untrusted files, so it is the riskiest component.
- `-protocol_whitelist file` on every ffprobe/ffmpeg call. This blocks HLS/concat tricks that read local files or fetch URLs (SSRF).
- The container format must be in an allowlist before any decoding (via ffprobe `format_name`).
- Every subprocess has a timeout. Celery has soft and hard time limits. Inputs and outputs live in a temp directory that is always removed.
- The worker container runs as a non-root user, with CPU and memory limits in compose, no published ports and `no-new-privileges`.
- Arguments are passed as a list to `subprocess.run` (no shell), and paths are server-generated.

## 7. Rate limits

Implementation: a Redis fixed-window counter (`INCR` + `EXPIRE`) as a FastAPI dependency returning `429` + `Retry-After`, plus nginx `limit_req` on `/api/v1/auth/` as a first coarse layer.

| Endpoint | Limit |
|---|---|
| `POST /auth/login` | 10/min per IP **and** 5/min per email |
| `POST /auth/register` | 5/h per IP |
| `POST /auth/refresh` | 30/min per IP |
| `POST /videos` (upload init) | 20/h per user |
| `POST /videos/{id}/comments` | 20/min per user |
| `POST /videos/{id}/reports` | 20/h per user |
| `GET /search`, `/search/suggestions` | 60/min per IP |
| `POST /videos/{id}/views` | 120/min per IP |

The client IP comes from `X-Forwarded-For`, honoured **only** from the proxy address in `FORWARDED_ALLOW_IPS` (nginx's fixed container address). nginx overwrites the header with `$remote_addr` instead of appending. Trusting every peer (`*`) would let any client choose its own IP and get a fresh rate-limit bucket per request. On cookie endpoints the Origin check runs before the limiter, so rejected cross-site requests do not consume the victim's quota. Change-password is also limited per account (5 per 15 min). Production refuses `RATE_LIMIT_ENABLED=false`.

## 8. HTTP and infrastructure hardening

- **Security headers (nginx):** `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`, plus `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`. HSTS is added only when TLS is configured. Fonts are self-hosted, so no third-party origins are needed.
- **CORS:** none in production (same origin). Dev allows only `http://localhost:5173`.
- **Only port 80 is published.** PostgreSQL, Redis and MinIO are reachable only on the internal network.
- **Secrets:** `deploy.sh` generates random JWT, media-token, DB and MinIO secrets into `.env` (`chmod 600`, git-ignored). The API refuses to start with placeholder secrets when `ENV=production`.
- **Containers:** non-root users, pinned image tags, minimal slim/alpine bases, health checks.
- **Errors:** no stack traces in responses. Passwords and tokens are never logged.
- **Supply chain:** pinned dependencies, plus `pip-audit` and `npm audit` in CI.

## 9. Known limitations (documented, not hidden)

- The default deployment is **plain HTTP** (a test machine without a domain). Tokens would then cross the network unencrypted. `deployment.md` will describe enabling TLS (certificate paths in `.env` → nginx 443 + HSTS + `COOKIE_SECURE=true`).
- Registration reveals whether an email is already taken (a UX trade-off, the same as YouTube). Login does not.
- The per-account login limit (5/min) means anyone who knows an email can delay that account's logins by a minute at a time. This is accepted in exchange for stopping distributed password guessing.
- Access JWTs stay valid for up to 15 minutes after logout or a password change (stateless by design). Bans, however, apply immediately because the user is loaded per request.
- A media URL copied while valid only works for a viewer who still passes `can_view`, so for a private video it does not work for anyone without a grant.
