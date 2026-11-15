# Session transcripts

The raw Claude Code transcripts of this project (`*.jsonl` from
`~/.claude/projects/c--Users-LOQ-Desktop-youtube-clone/`) are copied here **unmodified**
when the submission is packaged:

```bash
python scripts/package_submission.py      # copies the transcripts, then builds the zip with .git
```

They are copied at packaging time (not committed earlier) because a transcript keeps
growing until its session ends. The prompts inside them are also extracted verbatim to
[`../prompts/`](../prompts/).
