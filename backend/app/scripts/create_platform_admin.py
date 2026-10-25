"""Create a Duolink admin (there is no sign-up; access to the server is the proof).

    python -m app.scripts.create_platform_admin admin@duolink.app "Full Name"

The password comes from PLATFORM_ADMIN_PASSWORD, or a random one is printed once. The admin signs
in at admin.<BASE_DOMAIN>/admin and should change it there.
"""

import os
import secrets
import sys

from sqlalchemy import select

from app import services as _services  # noqa: F401 - registers session listeners
from app.core.db import SessionLocal
from app.core.security import MIN_PASSWORD_LENGTH
from app.models.platform import PlatformAdmin
from app.services.platform import auth

USAGE = 'usage: python -m app.scripts.create_platform_admin <email> "<full name>"'


def main(argv: list[str]) -> int:
    if len(argv) != 2 or "@" not in argv[0] or not argv[1].strip():
        print(USAGE)
        return 2
    email, full_name = argv[0].strip().lower(), argv[1]
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"PLATFORM_ADMIN_PASSWORD needs {MIN_PASSWORD_LENGTH} characters or more.")
        return 2
    with SessionLocal() as db:
        if db.execute(select(PlatformAdmin.id).where(PlatformAdmin.email == email)).first():
            print(f"An admin with {email} exists already.")
            return 1
        auth.create_admin(db, email, full_name, password)
    print(f"Created Duolink admin {email}.")
    if "PLATFORM_ADMIN_PASSWORD" not in os.environ:
        print(f"Password (shown once): {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
