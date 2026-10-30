"""Give a user a new random password from the server (for a forgotten owner password).

    python -m app.scripts.reset_password owner                 # the default company
    python -m app.scripts.reset_password owner --tenant acme   # another company

Needs access to the server, which is the proof of ownership. The new password is printed once;
the user's other sign-ins end and a lockout is cleared. The change is written to the audit log.
"""

import secrets
import sys

from sqlalchemy import select

from app import services as _services  # noqa: F401 - registers audit listeners
from app.core.db import SessionLocal
from app.core.errors import NotFoundError
from app.core.tenancy import current_tenant_id
from app.models.setup import AppUser
from app.services import tenants
from app.services import users as user_service

USAGE = "usage: python -m app.scripts.reset_password <username> [--tenant <company code>]"


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 3) or (len(argv) == 3 and argv[1] != "--tenant"):
        print(USAGE)
        return 2
    username = argv[0]
    with SessionLocal() as db:
        try:
            tenants.use_slug(db, argv[2] if len(argv) == 3 else None)
        except NotFoundError as exc:
            print(exc.message)
            return 1
        user = db.execute(
            select(AppUser).where(
                AppUser.tenant_id == current_tenant_id(db), AppUser.username == username
            )
        ).scalar_one_or_none()
        if user is None:
            print(f"No user called {username!r}.")
            return 1
        password = secrets.token_urlsafe(12)
        user_service.reset_password(db, user.id, password)
    print(f"New password for {username}: {password}")
    print("Sign in with it now and change it under your account.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
