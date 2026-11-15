"""Extract the prompts the user typed, verbatim, from a Claude Code session transcript.

Skips IDE context blocks, system reminders, task notifications, tool results and other
harness-generated turns, keeping only text the user wrote or pasted.
"""
import json
import sys
from pathlib import Path

AUTOMATED_PREFIXES = (
    "<ide_", "<system-reminder>", "<task-notification>", "[SYSTEM NOTIFICATION",
    "Your response above was stopped", "Tool loaded.", "<command-", "Caveat:",
)

transcript, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)
prompts = []
for line in transcript.read_text(encoding="utf-8").splitlines():
    rec = json.loads(line)
    attachment = rec.get("attachment")
    if (
        rec.get("type") == "attachment"
        and isinstance(attachment, dict)
        and attachment.get("type") == "queued_command"
        and (attachment.get("origin") or {}).get("kind") == "human"
    ):
        # A message the user sent while Claude was mid-turn (delivered with a tool result).
        prompt = attachment.get("prompt")
        rec = {"timestamp": attachment.get("timestamp") or rec.get("timestamp"),
               "type": "user", "message": {"content": prompt}}
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        continue
    content = rec.get("message", {}).get("content")
    blocks = [content] if isinstance(content, str) else [
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    ]
    texts = [t for t in blocks if t and not t.lstrip().startswith(AUTOMATED_PREFIXES)]
    if texts:
        prompts.append((rec.get("timestamp"), "\n\n".join(texts)))

prompts.sort(key=lambda item: item[0] or "")
for i, (ts, text) in enumerate(prompts, 1):
    path = out_dir / f"{i:02d}.md"
    path.write_text(
        f"<!-- Extracted verbatim from Claude Code session transcript; timestamp {ts} -->\n\n{text}\n",
        encoding="utf-8", newline="\n",
    )
    first = text.strip().splitlines()[-1][:70]
    print(f"{i:02d} {ts} chars={len(text):6d} last line: {first!r}")
