# AI-assisted development

How this project was built with Claude Code: roles, agent setup, the working loop, how results were verified, and what did not go to plan.

## 1. Roles

| Who | Role |
|---|---|
| Developer | Architect and reviewer: set the goals, approved the design, decided order (backend first), approved every push |
| Claude Code (main session) | Implementer: design docs, code, tests, infrastructure, verification, commits |
| `security-reviewer` subagent | Independent security review of finished stages (run twice) |
| `code-reviewer`, `test-engineer` subagents | Defined for diff review and negative-case tests ([`.claude/agents/`](../.claude/agents/)) |

## 2. Agent setup (submitted as-is)

| File | What it does |
|---|---|
| [`CLAUDE.md`](../CLAUDE.md) | Project rules loaded into every session: stack, commands, 8 architecture rules (layering, the single access policy, no mass assignment, keys from server ids, atomic counters, enqueue after commit…), security non-negotiables, testing rules ("never report a test result that was not run"), definition of done, git policy (no push without OK, no history rewrite) |
| [`.claude/settings.json`](../.claude/settings.json) | Permission allow-list (tests, lint, compose, read-only git) and deny-list (reading `.env`, force-push, `reset --hard`, `git clean`); PostToolUse hook |
| [`.claude/hooks/ruff_check.py`](../.claude/hooks/ruff_check.py) | Runs `ruff check` on every Python file Claude edits and feeds problems back immediately (it caught dozens of issues during writing) |
| [`.claude/agents/`](../.claude/agents/) | `security-reviewer`, `code-reviewer`, `test-engineer` with checklists and an evidence-based output format |
| [`.claude/skills/`](../.claude/skills/) | `stage` (one roadmap stage end-to-end), `verify` (all quality gates, real output only), `commit` (conventional commit of a verified change) |

No MCP servers were configured for this project (there is no `.mcp.json`).

## 3. The working loop

Every stage of [plan.md](plan.md) followed the same loop:

1. **Design first:** Stage 1 produced requirements, our own acceptance criteria (A1–F1 in [architecture.md](architecture.md#13-our-definition-of-works-correctly)), the data model, API, storage and security design, and the roadmap. Implementation started only after the architect's approval.
2. **Small, testable tasks**, each with its tests written together with the code, including negative authorization cases (401/403/404).
3. **Verify with real output:** ruff (lint + format), pytest against real PostgreSQL/Redis/MinIO, Vitest, CI on every push, and checks on the running production stack through nginx.
4. **Independent review:** the `security-reviewer` subagent audited finished stages; every finding was fixed with a regression test or explicitly documented.
5. **Docs updated** when the implementation deviated ([plan.md § 0](plan.md) lists every deviation and why).
6. **Small Conventional Commits** on a branch per stage, merged with `--no-ff` and tagged.

## 4. Verification evidence

| Check | Result |
|---|---|
| Backend tests (pytest, real services) | 346 passing |
| Frontend tests (Vitest + Testing Library) | 17 passing |
| CI (GitHub Actions: backend + frontend jobs) | green |
| Production stack through nginx | all services healthy; Range 206; storage headers hidden; private video 404 to strangers; copied media link 404 without the owner's cookie; worker has no token secrets and a read-only root |
| Smoke test (`scripts/smoke_test.sh`) | register, login and presigned upload pass; processing step pending (see § 6) |

## 5. What verification caught (that tests alone did not)

| Problem | Found by | Fix |
|---|---|---|
| Demo accounts used `.local` emails, which email validation rejects, so nobody could log in | Logging in on the deployed stack | `861ae42` + regression test |
| Worker crashed in the slim image: kombu imports `packaging` without declaring it (dev had it through pytest) | Starting the production stack | pinned in `e83571f` |
| nginx kept stale container IPs after restarts → 502 | Restarting services during the smoke test | per-request DNS, `e83571f` |
| Typo search missed long titles (`similarity` vs `word_similarity`) | Searching the real demo data | `2febd69` + regression test |
| A local variable shadowed a function after a refactor (12 tests failed) | Full test run | fixed before commit |
| `docker compose run` recreated dev containers without their ports | Mass test errors | isolated test compose project in `scripts/test.sh` |
| Smoke test signatures broke on Windows (CRLF from Python) | Running the smoke test | `tr -d '\r'` in the JSON helper |
| A commit message claimed template files were removed when they were not | Self-check after commit | corrected by a follow-up commit (`790be17`), history not rewritten |

## 6. Security reviews

1. **Stage 3 (auth):** 0 critical/high; 2 medium (session revocation race, spoofable `X-Forwarded-For`), 4 low. All fixed in `d36fc19` (+ the nginx side in `e83571f`).
2. **Stages 5–7 + deployment:** 0 critical; 1 high (public demo admin password), 2 medium (copied media links, worker holding all secrets), 11 low. Fixed in `b650f3b`, `519e7ab`, `c5319ea`, `dd9ae2d`; remaining limitations are listed in [security.md § 9](security.md#9-known-limitations-documented-not-hidden).

## 7. What did not go to plan (honestly)

- Several responses in the main session were **stopped by an automatic safety classifier** while writing specific pieces: the video processing Celery task, the comments service, a two-connection concurrency test, and the frontend API client with sign-in. Partial files were removed each time so the repository never contained broken code. These pieces are therefore still open:
  - `process_video` Celery task (the hardened ffmpeg wrapper, its tests and the housekeeping tasks exist),
  - the comments API (table, constraints and seed data exist),
  - frontend sign-in and the screens that depend on it (upload, Studio, moderation/admin, like/subscribe/comment actions).
- Network speed on the development machine made image pulls very slow (the Node image took over 10 minutes), which shaped the order of work.

## 8. Prompts and transcripts

- Prompts: [`ai/prompts/`](../ai/prompts/), extracted verbatim by [`scripts/extract_prompts.py`](../scripts/extract_prompts.py) (including messages sent mid-turn).
- Raw session transcripts: copied unmodified into `ai/sessions/` by `scripts/package_submission.py`, which also builds the submission archive.
