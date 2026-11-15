#!/usr/bin/env bash
# One-command deployment on a clean Ubuntu 22.04 / 24.04 machine.
#
#   ./deploy.sh             install Docker if missing, generate secrets, build, start,
#                           load demo data, verify health
#   ./deploy.sh --no-seed   same, without demo data
#
# Safe to run again: an existing .env (and its secrets) is never overwritten, the
# database is migrated, storage provisioning and seeding are idempotent.
set -euo pipefail
cd "$(dirname "$0")"

SEED=1
for arg in "$@"; do
  case "$arg" in
    --no-seed) SEED=0 ;;
    -h | --help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 2
      ;;
  esac
done

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() {
  printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2
  exit 1
}

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 || die "run as root or install sudo"
  SUDO="sudo"
fi

install_docker() {
  log "Installing Docker Engine and the Compose plugin (official Docker apt repository)"
  $SUDO apt-get update -y
  $SUDO apt-get install -y ca-certificates curl gnupg openssl
  $SUDO install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg |
    $SUDO gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
  $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" |
    $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
  $SUDO apt-get update -y
  $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin \
    docker-compose-plugin
  $SUDO systemctl enable --now docker
}

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  install_docker
fi

# Use sudo for docker only when the current user cannot reach the daemon.
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  DOCKER="$SUDO docker"
  $DOCKER info >/dev/null 2>&1 || die "Docker daemon is not reachable"
fi
compose() { $DOCKER compose "$@"; }

secret() { openssl rand -hex "$1"; }  # hex: safe inside URLs and .env

command -v openssl >/dev/null 2>&1 || $SUDO apt-get install -y openssl
umask 077
if [ ! -f .env ]; then
  log "Creating .env with freshly generated random secrets"
  cp .env.example .env
  sed -i "s|^APP_ENV=.*|APP_ENV=production|" .env
else
  log "Using the existing .env (real secrets are kept)"
fi
chmod 600 .env

# Every secret that is missing, empty or still a "change-me" placeholder gets a fresh
# random value, also in a hand-made .env copied from .env.example (review L11).
ensure_secret() {
  local name="$1" bytes="$2" current
  current="$(grep -E "^${name}=" .env | head -1 | cut -d= -f2- || true)"
  case "$current" in
    "" | change-me*)
      if grep -qE "^${name}=" .env; then
        sed -i "s|^${name}=.*|${name}=$(secret "$bytes")|" .env
      else
        printf '%s=%s\n' "$name" "$(secret "$bytes")" >>.env
      fi
      ;;
  esac
}
ensure_secret POSTGRES_PASSWORD 24
ensure_secret MINIO_ROOT_PASSWORD 24
ensure_secret MINIO_APP_SECRET_KEY 24
ensure_secret JWT_SECRET 32
ensure_secret MEDIA_TOKEN_SECRET 32
# Demo accounts get a random password, never a public default (review H1).
ensure_secret DEMO_PASSWORD 8

HTTP_PORT="$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || true)"
HTTP_PORT="${HTTP_PORT:-80}"

log "Building images and starting the stack (the first run downloads base images)"
compose up -d --build --wait

if [ "$SEED" = 1 ]; then
  log "Loading demo data (idempotent)"
  compose exec -T api python -m app.cli.seed
fi

log "Checking readiness through nginx"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/v1/health/ready" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done
[ "${READY:-0}" = 1 ] || die "the API did not become ready; see: docker compose logs api"

DEMO_PASSWORD_VALUE="$(grep -E '^DEMO_PASSWORD=' .env | cut -d= -f2-)"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-127.0.0.1}"
PORT_SUFFIX=""
[ "$HTTP_PORT" = 80 ] || PORT_SUFFIX=":${HTTP_PORT}"

cat <<EOF

  YouTube Clone is running.

    App      http://${HOST_IP}${PORT_SUFFIX}/
    Swagger  http://${HOST_IP}${PORT_SUFFIX}/docs
    Health   http://${HOST_IP}${PORT_SUFFIX}/api/v1/health/ready

  Demo accounts (password for all: ${DEMO_PASSWORD_VALUE}, also stored in .env as DEMO_PASSWORD):
    admin@example.com       administrator
    moderator@example.com   moderator
    alice@example.com       creator
    bob@example.com         creator
    viewer@example.com      viewer

  Logs:  docker compose logs -f api worker
  Stop:  docker compose down        (add -v to also delete all data)

EOF
