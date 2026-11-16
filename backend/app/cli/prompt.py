"""Reading a new password in the operator CLIs (create_admin, reset_password)."""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable

PasswordReader = Callable[[], str | None]


def read_new_password() -> str | None:
    """Interactive: asked twice without echo. Piped: the first line of stdin.

    Never taken from the command line, where it would end up in the shell history and
    the process list. Returns None when the two entries differ or nothing was given.
    """
    if not sys.stdin.isatty():
        line = sys.stdin.readline()
        # Windows PowerShell prefixes piped text with a BOM; it is not part of the password.
        return line.rstrip("\r\n").lstrip("﻿") or None
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat the new password: "):
        print("The passwords do not match.", file=sys.stderr)
        return None
    return first or None
