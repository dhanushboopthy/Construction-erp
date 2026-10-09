"""Give a user a new random password from the server (for a forgotten owner password).

    python -m app.scripts.reset_password owner

Needs access to the server, which is the proof of ownership. The new password is printed once;
the user's other sign-ins end and a lockout is cleared. The change is written to the audit log.
"""

import secrets
import sys

from sqlalchemy import select

from app import services as _services  # noqa: F401 - registers audit listeners
from app.core.db import SessionLocal
from app.core.tenancy import TENANT_ID
from app.models.setup import AppUser
from app.services import users as user_service


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.scripts.reset_password <username>")
        return 2
    with SessionLocal() as db:
        user = db.execute(
            select(AppUser).where(AppUser.tenant_id == TENANT_ID, AppUser.username == argv[0])
        ).scalar_one_or_none()
        if user is None:
            print(f"No user called {argv[0]!r}.")
            return 1
        password = secrets.token_urlsafe(12)
        user_service.reset_password(db, user.id, password)
    print(f"New password for {argv[0]}: {password}")
    print("Sign in with it now and change it under your account.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
