"""Set a new password for an account from the server shell.

    docker compose exec api python -m app.cli.reset_password someone@example.com

For operators: there is no e-mail based reset in this project, and the demo accounts
keep the password they were seeded with even if DEMO_PASSWORD changes later.

- The password is asked for interactively, twice, without echo. It is never taken from
  the command line, where it would end up in the shell history and the process list.
  For scripts it can be piped on stdin (`docker compose exec -T ... < file`).
- The registration policy applies (8-128 characters, not the email or handle).
- Every session of the account is signed out.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.cli.prompt import PasswordReader, read_new_password
from app.core.errors import BadRequestError
from app.db.session import get_sessionmaker
from app.models import User
from app.services import auth


def main(argv: list[str], reader: PasswordReader = read_new_password) -> int:
    if len(argv) != 1:
        print("usage: python -m app.cli.reset_password <email>", file=sys.stderr)
        return 2
    email = argv[0].strip().lower()
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account with email {email}.", file=sys.stderr)
            return 1
        password = reader()
        if not password:
            print("Password not changed.", file=sys.stderr)
            return 1
        try:
            auth.set_password(db, user, password)  # validates before changing anything
        except BadRequestError as exc:
            print(f"Password not changed: {exc.message}", file=sys.stderr)
            return 1  # nothing was modified; the session closes without a commit
        db.commit()
    print(f"Password changed for {email}; all of its sessions were signed out.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
