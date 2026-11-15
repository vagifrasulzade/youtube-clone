"""Promote an existing account to administrator.

    docker compose exec api python -m app.cli.create_admin someone@example.com

The public API can grant at most the moderator role (security review L3), so the
first and any further admins are created from the server's shell, which requires
operator access, not a web session.
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import User
from app.models.enums import ROLE_IDS, RoleName


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.cli.create_admin <email>", file=sys.stderr)
        return 2
    email = argv[0].strip().lower()
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account with email {email}; register it first.", file=sys.stderr)
            return 1
        user.role_id = ROLE_IDS[RoleName.ADMIN]
        db.commit()
    print(f"{email} is now an administrator.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
