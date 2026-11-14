"""PostToolUse hook: lint a Python file right after Claude edits it.

Reads the hook payload (JSON) from stdin. If the edited file is a backend Python
file and ruff is available, runs `ruff check` on it. Lint errors are written to
stderr with exit code 2, which Claude Code feeds back to the model so it fixes
them immediately. The hook never modifies files and is a no-op when ruff is missing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_DIR / "backend"


def find_ruff() -> str | None:
    candidates = [
        BACKEND_DIR / "venv" / "Scripts" / "ruff.exe",
        BACKEND_DIR / "venv" / "bin" / "ruff",
        BACKEND_DIR / ".venv" / "Scripts" / "ruff.exe",
        BACKEND_DIR / ".venv" / "bin" / "ruff",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ruff")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path or not file_path.endswith(".py"):
        return 0

    path = Path(file_path).resolve()
    if BACKEND_DIR not in path.parents or not path.is_file():
        return 0

    ruff = find_ruff()
    if ruff is None:
        return 0

    result = subprocess.run(  # noqa: S603 - fixed executable, list args, no shell
        [ruff, "check", "--quiet", "--output-format", "concise", str(path)],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"ruff check found problems in {path.name}:\n{result.stdout}{result.stderr}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
