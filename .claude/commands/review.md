---
description: Review a change with the code-reviewer agent, plus the security-reviewer when it touches a sensitive area
argument-hint: "[commit range, e.g. main..HEAD; default: uncommitted changes]"
---

Review the change `$ARGUMENTS` (if empty: the uncommitted working tree, `git diff` + untracked files).

1. List the changed files (`git diff --stat $ARGUMENTS`) and summarise the change in two lines.
2. Run the `code-reviewer` agent on it. Give it:
   - the diff range;
   - the relevant design docs (`docs/architecture.md` acceptance criteria, `docs/api.md`);
   - the tests that were actually run, with their real summary lines.
3. If any changed file is in auth, access, uploads, media delivery, moderation, admin, the worker
   or infra (`backend/app/services/{auth,access,uploads,media_*,moderation,admin}.py`,
   `backend/app/api/`, `backend/app/workers/`, `frontend/src/auth/`, `docker-compose.yml`,
   `infra/`), run the `security-reviewer` agent **in parallel** with the same context.
4. Merge both reports into one list ordered by severity, each entry with `file:line`, the problem
   and a concrete fix. Mark which findings you agree with and why.
5. Do not edit files in this command. Ask which findings to fix (default: all critical, high and
   medium ones), then fix them in separate, small commits with tests.
