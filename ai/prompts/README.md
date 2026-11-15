# Prompts

These are the prompts given to Claude Code for this project, **extracted verbatim** from the session transcripts (`~/.claude/projects/c--Users-LOQ-Desktop-youtube-clone/*.jsonl`) by [`scripts/extract_prompts.py`](../../scripts/extract_prompts.py). Only harness-generated content is skipped: IDE context, system reminders, task notifications and tool results. Messages the user sent while Claude was mid-turn (`queued_command` records) are included. The raw transcripts themselves go to `ai/sessions/` unmodified.

| # | Timestamp (UTC) | Prompt |
|---|---|---|
| 01 | 2026-11-14 14:36 | Task statement + master prompt: Stage 1 design (requirements, architecture, ER diagram, API, storage, security, roadmap, tests, git plan), then wait for review. "Backend first, then frontend; Claude is needed" |
| 02 | 2026-11-14 14:52 | Same prompt re-sent as the approval: "…set up Claude in the project and start" |
| 03 | 2026-11-14 14:59 | Same prompt again (sent mid-turn): "let's start on the backend" |
| 04, 06, 07, 08, 11, 14, 15, 17, 21, 24 | | "So, did you finish the whole backend?" (status checks) |
| 05 | 2026-11-14 16:20 | "Push main first, then all of these stages are needed" |
| 09, 16, 18, 19, 22, 25 | | "Continue" |
| 10 | 2026-11-14 17:26 | "CI check is failing: continue and fix it" |
| 12, 20, 23 | | "Yes (push)" |
| 13 | 2026-11-14 17:42 | "Continue and fix" |

Prompts are in Azerbaijani where the user wrote them that way. The translations in the table are summaries; the files hold the exact text.

Regenerate with:

```bash
python scripts/extract_prompts.py ~/.claude/projects/c--Users-LOQ-Desktop-youtube-clone/<session>.jsonl <out-dir>
```
