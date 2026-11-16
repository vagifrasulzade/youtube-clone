---
description: Build and start the full production stack, then run the end-to-end smoke test through nginx
argument-hint: "[--no-build]"
---

Check that the deployed app works end to end, exactly as a browser uses it.

1. Unless `$ARGUMENTS` contains `--no-build`, rebuild and start the stack:
   `docker compose up -d --build`
2. Wait until `docker compose ps` shows `api`, `worker` and `nginx` as healthy, then check
   `curl -s http://127.0.0.1/api/v1/health/ready` (database, redis and storage must be `ok`).
3. Run `bash scripts/smoke_test.sh`. It registers, logs in, uploads, waits for processing,
   streams with a Range request (206, and 404 for a copied link without the cookie), likes and
   comments.
4. Report the real output: the step lines and the final `OK` or `FAIL` line. On a failure, show
   the relevant `docker compose logs --tail=50 <service>` output and name the cause.

Do not change code or configuration to make the test pass, and do not report a step as passed
unless you saw it pass in this run.
