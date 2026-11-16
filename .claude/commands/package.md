---
description: Prepare the hand-in - refresh the verbatim prompts, run every quality gate, build the submission zip
---

Prepare the submission archive (`docs/plan.md`, day 10).

1. If `git status ai/prompts` shows uncommitted edits, stop and ask the user first: re-extracting
   rewrites those files. Then refresh the prompts: for each session transcript in
   `~/.claude/projects/c--Users-LOQ-Desktop-youtube-clone/*.jsonl`, run
   `python scripts/extract_prompts.py <transcript> ai/prompts` and show `git diff --stat ai/prompts`.
   The prompts must stay verbatim; never edit their text by hand.
2. Run the `verify` skill (ruff, the full backend suite, frontend type-check/lint/test/build) and
   quote the real summary lines. Stop here if anything fails.
3. Show `git status`. Uncommitted changes would end up in the zip but not in the git history, so
   list them and ask whether to commit them first. Never commit `.env`.
4. Run `python scripts/package_submission.py`. It copies the raw `.jsonl` transcripts unmodified
   into `ai/sessions/` and zips the repository including `.git`, without `.env`, virtualenvs,
   `node_modules` and build output.
5. Report the archive path, its size, the number of files and the transcript checksums it printed.

Do not push or tag anything in this command.
