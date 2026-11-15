"""Build the submission archive.

1. Copies every Claude Code session transcript of this project (*.jsonl), byte for
   byte, into ai/sessions/ (the task requires the tool's original files).
2. Zips the repository INCLUDING .git (full commit history), excluding only local
   environments, build output and secrets.

    python scripts/package_submission.py                  # -> ../youtube-clone-submission.zip
    python scripts/package_submission.py --out my.zip
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SESSIONS_SRC = Path.home() / ".claude" / "projects" / "c--Users-LOQ-Desktop-youtube-clone"
SESSIONS_DST = REPO / "ai" / "sessions"

EXCLUDED_DIRS = {"venv", ".venv", "node_modules", "dist", "__pycache__", ".pytest_cache", ".ruff_cache"}
EXCLUDED_FILES = {".env"}  # secrets; .env.example is kept


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def copy_sessions() -> list[Path]:
    SESSIONS_DST.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(SESSIONS_SRC.glob("*.jsonl")):
        dst = SESSIONS_DST / src.name
        shutil.copy2(src, dst)  # unmodified, timestamps preserved
        copied.append(dst)
        print(f"session {src.name}  {src.stat().st_size:>10} bytes  sha256 {sha256(dst)}")
    if not copied:
        print(f"WARNING: no transcripts found in {SESSIONS_SRC}", file=sys.stderr)
    return copied


def included(path: Path) -> bool:
    rel = path.relative_to(REPO)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    return path.name not in EXCLUDED_FILES


def build_zip(out: Path) -> int:
    count = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(REPO.rglob("*")):
            if path.is_file() and included(path):
                archive.write(path, Path(REPO.name) / path.relative_to(REPO))
                count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO.parent / "youtube-clone-submission.zip")
    args = parser.parse_args()

    copy_sessions()
    files = build_zip(args.out)
    print(f"archive {args.out}  ({files} files, .git included, .env and local envs excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
