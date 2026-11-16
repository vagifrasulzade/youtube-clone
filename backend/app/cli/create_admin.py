"""Create or promote an administrator from the server shell.

    docker compose exec api python -m app.cli.create_admin admin@example.com [handle]

- An existing account is promoted to admin; its password does not change.
- If there is no account with that email, one is created: the password is asked twice
  without echo, and the handle defaults to the email's local part (made valid and
  unique). Registration's rules apply (valid email, 8-128 character password that is
  not the email or handle).

The public API can grant at most the moderator role (security review L3), so admins are
created only here, which requires shell access to the server, not a web session.
"""

from __future__ import annotations

import re
import sys

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli.prompt import PasswordReader, read_new_password
from app.core.errors import ConflictError
from app.db.session import get_sessionmaker
from app.models import Channel, User
from app.models.enums import ROLE_IDS, RoleName
from app.schemas.auth import RegisterRequest
from app.services import auth

USAGE = "usage: python -m app.cli.create_admin <email> [handle]"


def _default_handle(db: Session, email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:26]
    if len(base) < 3:
        base = f"{base}admin"[:26]
    candidate, n = base, 1
    while db.scalar(select(Channel.id).where(Channel.handle == candidate)) is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _create(db: Session, email: str, handle: str | None, reader: PasswordReader) -> User | None:
    password = reader()
    if not password:
        print("No account created.", file=sys.stderr)
        return None
    try:
        request = RegisterRequest(
            email=email,
            password=password,
            handle=handle or _default_handle(db, email),
            display_name=(handle or email.split("@")[0])[:50],
        )
    except ValidationError as exc:
        # Only the rule that failed; the submitted values (the password) are not echoed.
        reasons = "; ".join(
            f"{'.'.join(map(str, error['loc'])) or 'input'}: {error['msg']}"
            for error in exc.errors()
        )
        print(f"No account created: {reasons}", file=sys.stderr)
        return None
    try:
        return auth.register(
            db,
            email=request.email,
            password=request.password,
            handle=request.handle,
            display_name=request.display_name,
        )
    except ConflictError as exc:
        print(f"No account created: {exc.message}", file=sys.stderr)
        return None


def main(argv: list[str], reader: PasswordReader = read_new_password) -> int:
    if len(argv) not in (1, 2):
        print(USAGE, file=sys.stderr)
        return 2
    email = argv[0].strip().lower()
    handle = argv[1].strip().lstrip("@").lower() if len(argv) == 2 else None
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == email))
        created = user is None
        if user is None:
            print(f"No account with email {email} yet: creating one.")
            user = _create(db, email, handle, reader)
            if user is None:
                return 1
        user.role_id = ROLE_IDS[RoleName.ADMIN]
        db.commit()
        channel_handle = user.channel.handle
    if created:
        print(f"Created administrator {email} (@{channel_handle}). Sign in with this password.")
    else:
        print(f"{email} is now an administrator (password unchanged).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
