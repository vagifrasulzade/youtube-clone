---
description: Load the demo data into the running stack (15 accounts, 31 generated videos), optionally re-rendering existing demo videos
argument-hint: "[--refresh-media]"
---

Load or update the demo data in the running stack.

1. Make sure `api` is running and healthy (`docker compose ps`). If the code changed since the
   image was built, rebuild it first: `docker compose up -d --build --no-deps api`.
2. Run `docker compose exec -T api python -m app.cli.seed $ARGUMENTS`.
   - Without arguments it only adds missing demo accounts and videos. It never changes an
     existing password or anyone's data.
   - `--refresh-media` also re-renders the files of existing demo videos, keeping their likes,
     comments and views.
3. Report the summary line it printed (new accounts, new videos, re-rendered videos). Then check
   `curl -s "http://127.0.0.1/api/v1/videos?limit=50"` and report how many videos and channels
   the home feed shows.

The demo password comes from `DEMO_PASSWORD` in `.env`. Never print or read `.env`: tell the user
where to find the password instead.
