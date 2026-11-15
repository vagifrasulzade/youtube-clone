# Deployment

## Prerequisites

- Ubuntu 22.04 or 24.04 (x86_64 or arm64), 2+ CPU cores, 4 GB RAM, 10 GB free disk.
- Outbound internet access on the first run (Docker packages, base images, Python/npm packages).
- `sudo` rights (only if Docker is not installed yet or the user is not in the `docker` group).
- A free TCP port for the web server: 80 by default, configurable through `HTTP_PORT`.

## One command

```bash
./deploy.sh            # or: ./deploy.sh --no-seed  (no demo data)
```

What it does, in order:

1. Installs Docker Engine and the Compose plugin from Docker's official apt repository, if missing.
2. Creates `.env` from `.env.example` with **freshly generated random secrets** (`openssl rand -hex`), mode `600`. An existing `.env` is never overwritten, so re-running keeps your data and secrets.
3. `docker compose up -d --build --wait` builds the images and starts the services in dependency order, waiting for health checks:

   ```
   postgres, redis, minio (healthy)
     -> minio-init  (buckets, 2-day lifecycle on raw uploads, least-privilege app user)
     -> migrate     (alembic upgrade head)
     -> api, worker, beat
     -> nginx       (the only published port)
   ```

4. Loads demo data (`python -m app.cli.seed`). Idempotent: it does nothing when the demo admin already exists.
5. Checks `/api/v1/health/ready` through nginx and prints the URLs and demo accounts.

Then run the end-to-end check:

```bash
scripts/smoke_test.sh                       # register -> login -> upload -> process -> watch -> like -> comment
BASE_URL=http://<host>:<port> scripts/smoke_test.sh
```

## Services

| Service | Role | Published |
|---|---|---|
| `nginx` | SPA, reverse proxy, upload pass-through to MinIO, X-Accel media delivery, security headers | `HTTP_PORT` (80) |
| `api` | FastAPI (uvicorn, 2 workers) | internal |
| `worker` | Celery worker (media processing, object deletion) | internal |
| `beat` | Celery scheduler (stale-draft cleanup, watchdog) | internal |
| `migrate`, `minio-init` | one-shot setup jobs | — |
| `postgres` | PostgreSQL 17, volume `postgres-data` | internal |
| `redis` | queue, rate limits, view dedupe (ephemeral) | internal |
| `minio` | object storage, volume `minio-data` | internal |

The internal network uses the fixed subnet `172.30.250.0/24`, with nginx at `172.30.250.10`. The API trusts `X-Forwarded-For` only from that address.

## Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `HTTP_PORT` | Public port of nginx |
| `APP_ENV` | `production` refuses weak or default secrets and a disabled rate limiter |
| `POSTGRES_*` | Database credentials |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Storage root account, used **only** by `minio-init` |
| `MINIO_APP_ACCESS_KEY` / `MINIO_APP_SECRET_KEY` | Least-privilege storage user for api/worker |
| `JWT_SECRET`, `MEDIA_TOKEN_SECRET` | Two different random values of 32+ characters |
| `COOKIE_SECURE` | `true` only when served over HTTPS |
| `MAX_UPLOAD_BYTES` | Upload limit (default 2 GiB), enforced by the storage upload policy |
| `MINIO_IMAGE`, `MINIO_CLIENT_IMAGE` | Override the pinned storage images (see below) |

## Operations

```bash
docker compose ps                      # status and health
docker compose logs -f api worker      # JSON logs with request ids
docker compose exec api python -m app.cli.seed
docker compose down                    # stop (data kept in volumes)
docker compose down -v                 # stop AND delete all data
git pull && ./deploy.sh                # upgrade: rebuild, migrate, restart
```

Backups: `docker compose exec postgres pg_dump -U youtube youtube > backup.sql`, plus a copy of the `minio-data` volume (or `mc mirror` of the `yt-media` bucket).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` for 80 | Set `HTTP_PORT=8080` in `.env`, then re-run `./deploy.sh` |
| `Pool overlaps with other one on this address space` | Another network uses `172.30.250.0/24`. Change the subnet and `FORWARDED_ALLOW_IPS`/`ipv4_address` in `docker-compose.yml` |
| `permission denied ... docker.sock` | Re-run with `sudo`, or add the user to the `docker` group and log in again |
| First build is slow | Base images and packages are downloaded once; later runs are cached |
| Storage image cannot be pulled | Upstream MinIO no longer publishes community images. The stack uses Chainguard's source build pinned by digest. Set `MINIO_IMAGE`/`MINIO_CLIENT_IMAGE` to another S3-compatible MinIO build if needed |
| A video stays `queued` | `docker compose logs worker`. The watchdog re-enqueues queued videos every 5 minutes |
| `health/ready` returns 503 | The body names the failing dependency (`database`, `redis`, `storage`); check that service's logs |

## HTTPS

The default deployment serves plain HTTP, which suits a test machine without a domain. For production, put TLS in front: either terminate it in nginx (add a `listen 443 ssl` server with your certificate and enable HSTS) or use a TLS-terminating load balancer. Then set `COOKIE_SECURE=true` so the refresh cookie is only sent over HTTPS.
