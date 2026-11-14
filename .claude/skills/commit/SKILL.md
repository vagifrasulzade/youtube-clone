---
name: commit
description: Create one small Conventional Commit for a reviewed, verified change. Use after the verify skill passed for the change being committed.
---

# Commit a change

1. `git status` and `git diff --staged`: stage **only** the files belonging to this one logical change. Never stage `.env`, secrets, `venv/`, `node_modules/`, build output or large media.
2. Confirm that the `verify` skill passed for this change in this session. If not, run it first.
3. Write the message:
   ```
   <type>(<scope>): <imperative summary, ≤ 72 chars>

   <why the change was made and anything a reviewer must know: decisions,
   trade-offs, follow-ups. Wrap at ~72 chars.>

   Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
   ```
   - Types: `feat`, `fix`, `test`, `docs`, `refactor`, `build`, `ci`, `chore`, `perf`.
   - Scopes: `backend`, `frontend`, `db`, `infra`, `ai`, `docs`.
4. Commit on the current stage branch, never directly on `main`.
5. Show `git log --oneline -1`. **Do not push** unless the architect explicitly asked for it.
