# API specification

> **Status: Approved — Stage 1, 2026-11-14.** The live, authoritative contract will be the generated OpenAPI: **Swagger UI at `/docs`**, ReDoc at `/redoc`, JSON at `/openapi.json`. This document is the design used to build it.

## Conventions

- Base path `/api/v1`. JSON in and out (except multipart image uploads and media streams).
- Auth: `Authorization: Bearer <access JWT>`. The refresh token travels only as an HttpOnly cookie scoped to `/api/v1/auth`.
- **Errors** always use one envelope:
  ```json
  { "error": { "code": "video_not_found", "message": "Video not found", "details": null } }
  ```
- Status codes: `400` business rule, `401` missing or invalid token, `403` authenticated but not allowed, **`404` also for resources the caller may not know exist** (private videos), `409` conflict or state, `413` too large, `422` validation, `429` rate limit (+ `Retry-After`).
- Pagination:
  - Infinite lists (feed, comments, channel videos, history) use **keyset**: `?limit=24&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." | null }`.
  - Numbered lists (search, studio, moderation, admin) use `?page=1&page_size=20` → `{ "items": [...], "total": 123, "page": 1, "page_size": 20 }`.
- Limits: `limit` and `page_size` are capped at 50.

Auth column: **—** anonymous allowed (optional auth personalizes the response) · **U** signed in · **O** owner of the resource · **M** moderator or admin · **A** admin.

## Auth

| Method | Path | Auth | Request → Response | Notes |
|---|---|---|---|---|
| POST | `/auth/register` | — | `{email, password, handle, display_name}` → `201 {access_token, expires_in, user}` + refresh cookie | Creates user + channel. Rate limit 5/h per IP |
| POST | `/auth/login` | — | `{email, password}` → `200 {access_token, expires_in, user}` + cookie | Generic error on failure. 10/min per IP, 5/min per email |
| POST | `/auth/refresh` | cookie | → `200 {access_token, expires_in}` + rotated cookie | Reuse of an old token revokes the family |
| POST | `/auth/logout` | cookie | → `204` | Revokes the family, clears the cookie |
| GET | `/auth/me` | U | → `{id, email, role, channel: {...}}` | |
| POST | `/auth/change-password` | U | `{current_password, new_password}` → `200 {access_token, expires_in, user}` + new cookie | Revokes every other session. 5 per 15 min per account |

## Videos

| Method | Path | Auth | Request → Response | Notes |
|---|---|---|---|---|
| GET | `/videos` | — | `?cursor&limit` → `Page[VideoCard]` | Home feed: public, ready, not hidden |
| POST | `/videos` | U | `{filename, content_type, size_bytes, title?}` → `201 {video, upload: {url, fields, expires_at}}` | Creates a **private draft** plus a presigned POST policy. 20/h per user |
| POST | `/videos/{id}/upload-complete` | O | → `202 {status: "queued"}` | Verifies the object exists, its size and magic bytes, then enqueues. `409` if missing or in the wrong state |
| GET | `/videos/{id}` | — | → `VideoDetail` | `404` unless `can_view`. Includes `stream_url`, `thumbnail_url`, `my_reaction`, `is_subscribed`, `can_edit` |
| GET | `/videos/{id}/status` | O | → `{status, progress, error}` | Polled by the upload dialog |
| PATCH | `/videos/{id}` | O | `{title?, description?, visibility?, thumbnail?: "auto_1"…"auto_3" \| "custom"}` → `VideoDetail` | |
| PUT | `/videos/{id}/thumbnail` | O | multipart `file` (jpeg/png/webp ≤ 2 MB) → `VideoDetail` | Re-encoded server-side |
| DELETE | `/videos/{id}` | O, A | → `204` | Objects removed asynchronously. Admin deletion is audited |
| GET | `/videos/{id}/related` | — | `?limit` → `VideoCard[]` | Title similarity, then the same channel, then popular |
| PUT | `/videos/{id}/reaction` | U | `{value: "like" \| "dislike"}` → `{like_count, dislike_count, my_reaction}` | Idempotent. Requires `can_view` |
| DELETE | `/videos/{id}/reaction` | U | → same shape | |
| POST | `/videos/{id}/views` | — | → `202` | Deduped per viewer per 24 h |
| GET | `/videos/{id}/permissions` | O | → `[{user_id, handle, name, granted_at}]` | |
| POST | `/videos/{id}/permissions` | O | `{handle}` → `201` | Grants access to a private video |
| DELETE | `/videos/{id}/permissions/{user_id}` | O | → `204` | Takes effect on the next request |
| POST | `/videos/{id}/reports` | U | `{reason, details?}` → `201` | `409` if this user already has an open report. 20/h per user |

`VideoCard` = `{id, title, thumbnail_url, duration_seconds, view_count, published_at, channel: {handle, name, avatar_url}}`

## Comments

| Method | Path | Auth | Request → Response | Notes |
|---|---|---|---|---|
| GET | `/videos/{id}/comments` | — | `?sort=newest\|oldest&cursor` → `Page[Comment]` | Top level only, with `reply_count` |
| POST | `/videos/{id}/comments` | U | `{body, parent_id?}` → `201 Comment` | A reply must be to a top-level comment on the same video. 20/min per user |
| GET | `/comments/{id}/replies` | — | `?cursor` → `Page[Comment]` | |
| PATCH | `/comments/{id}` | author | `{body}` → `Comment` | Sets `edited_at` |
| DELETE | `/comments/{id}` | author, video owner, M | → `204` | Moderator deletions are audited |

## Channels & subscriptions

| Method | Path | Auth | Request → Response |
|---|---|---|---|
| GET | `/channels/{handle}` | — | → `{id, handle, name, description, avatar_url, banner_url, subscriber_count, video_count, joined_at, is_subscribed, is_owner}` |
| GET | `/channels/{handle}/videos` | — | `?sort=latest\|popular\|oldest&cursor` → `Page[VideoCard]` |
| GET | `/channels/{handle}/playlists` | — | → `Page[PlaylistCard]` |
| PATCH | `/channels/me` | U | `{name?, description?, handle?}` → `Channel` |
| PUT | `/channels/me/avatar` · `/channels/me/banner` | U | multipart image → `Channel` |
| PUT | `/channels/{handle}/subscription` | U | → `{subscribed: true, subscriber_count}` (idempotent; `400` for your own channel) |
| DELETE | `/channels/{handle}/subscription` | U | → `{subscribed: false, subscriber_count}` |

## Me / library / studio

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/me/subscriptions` | U | Channels I follow (sidebar) |
| GET | `/me/feed/subscriptions` | U | `Page[VideoCard]` from subscribed channels |
| GET / DELETE | `/me/history` | U | Watch history / clear it |
| GET | `/me/liked` | U | Liked videos |
| GET | `/me/playlists` | U | My playlists (for "Save to playlist") |
| GET | `/me/shared` | U | Private videos shared with me |
| GET | `/studio/videos` | U | `?status&visibility&q&page` → my videos in every state, including `processing_error` and `is_hidden` |

## Playlists

| Method | Path | Auth | Request → Response |
|---|---|---|---|
| POST | `/playlists` | U | `{title, description?, visibility}` → `201 Playlist` |
| GET | `/playlists/{id}` | — | → playlist + items. Items the viewer cannot see appear as `{id: null, title: "Private video"}`. A private playlist returns `404` to others |
| PATCH / DELETE | `/playlists/{id}` | O | |
| POST | `/playlists/{id}/videos` | O | `{video_id}` → `201` (the owner must be able to view the video) |
| DELETE | `/playlists/{id}/videos/{video_id}` | O | → `204` |
| PUT | `/playlists/{id}/videos` | O | `{video_ids: [...]}`, a full permutation → reorder |

## Search

| Method | Path | Auth | Request → Response |
|---|---|---|---|
| GET | `/search` | — | `?q=(1–100 chars)&sort=relevance\|date\|views&page&page_size` → `Page[VideoCard + description_snippet]`. 60/min per IP |
| GET | `/search/suggestions` | — | `?q` → up to 10 strings (public titles only) |

## Media (consumed by `<video>` / `<img>`, not JSON)

URLs are produced by the API inside responses. Clients never build them.

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| GET | `/media/videos/{id}/stream?t=<media token>` | token | Re-checks `can_view`, then `X-Accel-Redirect` → nginx streams `playback.mp4` from MinIO. Honors `Range` → `206` |
| GET | `/media/videos/{id}/thumbnail?v=<version>[&t=]` | token if not public | JPEG. Public: `Cache-Control: public, max-age=3600`. Otherwise `private, no-store` |
| GET | `/media/videos/{id}/thumbnails/{n}?t=` | token (owner) | Auto candidates 1–3 for the Studio picker |
| GET | `/media/channels/{id}/avatar?v=` · `/banner?v=` | — | Public images |

## Moderation (M)

| Method | Path | Request → Response |
|---|---|---|
| GET | `/moderation/reports` | `?status=open&reason&page` → reports with a video summary and report count per video |
| GET | `/moderation/reports/{id}` | → report + video detail (staff can view private and hidden videos) |
| POST | `/moderation/reports/{id}/resolve` | `{action: "none" \| "hide_video", note}` → closes this and other open reports on the same video if hidden |
| POST | `/moderation/reports/{id}/dismiss` | `{note}` |
| POST | `/moderation/videos/{id}/hide` | `{reason}` → audited |
| POST | `/moderation/videos/{id}/restore` | `{reason}` → audited |
| GET | `/moderation/actions` | `?target_type&actor&page` → audit log |

## Admin (A)

| Method | Path | Request → Response |
|---|---|---|
| GET | `/admin/stats` | → `{users, videos_by_status, views_total, storage_bytes, open_reports, signups_7d}` |
| GET | `/admin/users` | `?q&role&banned&page` |
| PATCH | `/admin/users/{id}/role` | `{role}`. You cannot change your own role, and the last admin cannot be demoted. Audited |
| POST | `/admin/users/{id}/ban` · `/unban` | `{reason}`. Not yourself, and not another admin (demote first). Revokes sessions. Audited |
| GET | `/admin/videos` | `?q&status&visibility&hidden&page` |
| DELETE | `/videos/{id}` | Admins delete through the owner route; the deletion is audited (there is no separate admin route) |

## Health

| Method | Path | Response |
|---|---|---|
| GET | `/health/live` | `200 {status: "ok"}` |
| GET | `/health/ready` | `200` / `503` with `{db, redis, storage}` checks |
