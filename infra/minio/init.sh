#!/bin/sh
# One-shot MinIO setup, safe to re-run on every deploy (idempotent):
#   - two private buckets (raw uploads / processed media), no anonymous access
#   - raw uploads expire after 2 days (abandoned or failed uploads clean themselves up)
#   - a least-privilege application user limited to those two buckets
# Only this container ever uses the MinIO root credentials.
set -eu

: "${MINIO_ROOT_USER:?}" "${MINIO_ROOT_PASSWORD:?}"
: "${MINIO_APP_ACCESS_KEY:?}" "${MINIO_APP_SECRET_KEY:?}"
UPLOADS_BUCKET="${UPLOADS_BUCKET:-yt-uploads}"
MEDIA_BUCKET="${MEDIA_BUCKET:-yt-media}"
MINIO_URL="${MINIO_URL:-http://minio:9000}"
export MC_CONFIG_DIR="${MC_CONFIG_DIR:-/tmp/.mc}"

echo "minio-init: waiting for ${MINIO_URL}"
i=0
until mc alias set local "$MINIO_URL" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "minio-init: MinIO not reachable after 60s" >&2
    exit 1
  fi
  sleep 1
done

for bucket in "$UPLOADS_BUCKET" "$MEDIA_BUCKET"; do
  mc mb --ignore-existing "local/${bucket}"
  mc anonymous set none "local/${bucket}"
done

# Lifecycle: expire raw uploads after 2 days (import replaces the whole config -> idempotent).
cat > /tmp/uploads-lifecycle.json <<EOF
{"Rules": [{"ID": "expire-raw-uploads", "Status": "Enabled",
            "Filter": {"Prefix": ""}, "Expiration": {"Days": 2}}]}
EOF
mc ilm import "local/${UPLOADS_BUCKET}" < /tmp/uploads-lifecycle.json

# Least-privilege policy for the API and worker.
cat > /tmp/yt-app-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${UPLOADS_BUCKET}/*", "arn:aws:s3:::${MEDIA_BUCKET}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": ["arn:aws:s3:::${UPLOADS_BUCKET}", "arn:aws:s3:::${MEDIA_BUCKET}"]
    }
  ]
}
EOF
mc admin policy create local yt-app /tmp/yt-app-policy.json
mc admin user add local "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY"
# "attach" fails if already attached; that is the desired end state, so tolerate it.
mc admin policy attach local yt-app --user "$MINIO_APP_ACCESS_KEY" 2>/dev/null || true

echo "minio-init: done (buckets ${UPLOADS_BUCKET}, ${MEDIA_BUCKET}; app user ready)"
