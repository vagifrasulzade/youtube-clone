#!/usr/bin/env bash
# End-to-end check of a deployed stack, through nginx, exactly as a browser would:
#   register -> login -> upload (presigned POST) -> processing -> watch (Range 206)
#   -> like -> comment
#
#   scripts/smoke_test.sh                 # against http://127.0.0.1
#   BASE_URL=http://10.0.0.5:8080 scripts/smoke_test.sh
#
# Needs: curl, python3 (JSON parsing), ffmpeg OR docker (to make a tiny test clip).
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1}"
API="${BASE_URL}/api/v1"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

step() { printf '\033[1;34m[%s]\033[0m %s\n' "$1" "$2"; }
fail() {
  printf '\033[1;31mFAIL:\033[0m %s\n' "$*" >&2
  exit 1
}
# Python on Windows prints CRLF; a stray CR would corrupt the signed form values.
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" | tr -d '\r'; }

# --- a 3-second test clip ------------------------------------------------------------
CLIP="$WORK/clip.mp4"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -v error -f lavfi -i testsrc2=size=640x360:rate=25 \
    -f lavfi -i sine=frequency=440 -t 3 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
    -movflags +faststart "$CLIP"
else
  docker compose exec -T api sh -c 'ffmpeg -hide_banner -v error -f lavfi -i testsrc2=size=640x360:rate=25 \
    -f lavfi -i sine=frequency=440 -t 3 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest \
    -movflags frag_keyframe+empty_moov -f mp4 pipe:1' >"$CLIP"  # pipes need fragmented MP4
fi
SIZE="$(wc -c <"$CLIP" | tr -d ' ')"
[ "$SIZE" -gt 1000 ] || fail "could not create a test clip"

SUFFIX="$(date +%s)$RANDOM"
EMAIL="smoke${SUFFIX}@example.com"
PASSWORD="smoke-test-password-1"

step 1 "register ${EMAIL}"
curl -fsS -c "$WORK/cookies" -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\",\"handle\":\"smoke${SUFFIX}\",\"display_name\":\"Smoke Test\"}" \
  "${API}/auth/register" >"$WORK/register.json" || fail "registration"

step 2 "login"
TOKEN="$(curl -fsS -c "$WORK/cookies" -H 'Content-Type: application/json' \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}" "${API}/auth/login" |
  json 'd["access_token"]')" || fail "login"
AUTH="Authorization: Bearer ${TOKEN}"

step 3 "create upload draft and POST the file to storage"
curl -fsS -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"filename\":\"smoke.mp4\",\"content_type\":\"video/mp4\",\"size_bytes\":${SIZE},\"title\":\"Smoke test ${SUFFIX}\"}" \
  "${API}/videos" >"$WORK/draft.json" || fail "upload draft"
VIDEO_ID="$(json 'd["video"]["id"]' <"$WORK/draft.json")"
UPLOAD_URL="$(json 'd["upload"]["url"]' <"$WORK/draft.json")"
FORM_ARGS=()
while IFS= read -r field; do FORM_ARGS+=(-F "$field"); done < <(
  json '"\n".join(f"{k}={v}" for k, v in d["upload"]["fields"].items())' <"$WORK/draft.json"
)
# Relative path from inside $WORK: works with any curl build (incl. Windows curl.exe).
(cd "$WORK" && curl -fsS "${FORM_ARGS[@]}" -F "file=@clip.mp4;type=video/mp4"   "${BASE_URL}${UPLOAD_URL}") || fail "storage upload"
curl -fsS -X POST -H "$AUTH" "${API}/videos/${VIDEO_ID}/upload-complete" >/dev/null ||
  fail "upload-complete"

step 4 "wait for processing (up to 3 minutes)"
for _ in $(seq 1 90); do
  STATUS="$(curl -fsS -H "$AUTH" "${API}/videos/${VIDEO_ID}/status" | json 'd["status"]')"
  case "$STATUS" in
    ready) break ;;
    failed) fail "processing failed: $(curl -fsS -H "$AUTH" "${API}/videos/${VIDEO_ID}/status")" ;;
  esac
  sleep 2
done
[ "$STATUS" = ready ] || fail "video still '${STATUS}' after 3 minutes (is the worker running?)"

step 5 "watch: detail + Range request returns 206"
STREAM="$(curl -fsS -H "$AUTH" "${API}/videos/${VIDEO_ID}" | json 'd["stream_url"]')"
# Like a browser: the yt_media cookie from login goes along with the media request.
CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$WORK/cookies" -H 'Range: bytes=0-1023'   "${BASE_URL}${STREAM}")"
[ "$CODE" = 206 ] || fail "expected 206 for a Range request, got ${CODE}"
# The same link copied elsewhere (no cookie) must not play.
CODE="$(curl -s -o /dev/null -w '%{http_code}' -H 'Range: bytes=0-1023' "${BASE_URL}${STREAM}")"
[ "$CODE" = 404 ] || fail "a copied media link without the cookie returned ${CODE}, expected 404"

step 6 "like"
LIKES="$(curl -fsS -X PUT -H "$AUTH" -H 'Content-Type: application/json' -d '{"value":"like"}' \
  "${API}/videos/${VIDEO_ID}/reaction" | json 'd["like_count"]')"
[ "$LIKES" = 1 ] || fail "like_count is ${LIKES}"

step 7 "comment"
curl -fsS -H "$AUTH" -H 'Content-Type: application/json' -d '{"body":"Smoke test comment"}' \
  "${API}/videos/${VIDEO_ID}/comments" >/dev/null || fail "comment"

printf '\033[1;32mOK\033[0m register -> login -> upload -> process -> watch -> like -> comment\n'
