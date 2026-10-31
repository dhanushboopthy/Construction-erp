"""Create a Duolink admin (there is no sign-up; access to the server is the proof).

    python -m app.scripts.create_platform_admin admin@duolink.app "Full Name" [--role support]

`--role` is `super_admin` (the default, because this command creates the first admin) or
`support` (read-only). The password comes from PLATFORM_ADMIN_PASSWORD, or a random one is
printed once. The admin signs in at admin.<BASE_DOMAIN>/admin and should change it there. Further
staff are added by a Super Admin on the Staff page.
"""

import argparse
import os
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services as _services  # noqa: F401 - registers session listeners
from app.core.db import SessionLocal
from app.core.security import MIN_PASSWORD_LENGTH
from app.models.enums import PlatformRole
from app.models.platform import PlatformAdmin
from app.services.platform import auth


def create(db: Session, email: str, full_name: str, password: str, role: PlatformRole) -> str:
    """Create the admin; returns a message for the operator. Exit status: 0 ok, 1 exists, 2 bad."""
    email = email.strip().lower()
    if "@" not in email or not full_name.strip():
        raise ValueError("an email address and a full name are needed")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"the password needs {MIN_PASSWORD_LENGTH} characters or more")
    if db.execute(select(PlatformAdmin.id).where(PlatformAdmin.email == email)).first():
        raise FileExistsError(f"An admin with {email} exists already.")
    auth.create_admin(db, email, full_name, password, role=role)
    return f"Created Duolink admin {email} ({role.value})."


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="create_platform_admin", description=__doc__)
    parser.add_argument("email")
    parser.add_argument("full_name")
    parser.add_argument(
        "--role",
        choices=[role.value for role in PlatformRole],
        default=PlatformRole.SUPER_ADMIN.value,
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    password = os.environ.get("PLATFORM_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    try:
        with SessionLocal() as db:
            print(create(db, args.email, args.full_name, password, PlatformRole(args.role)))
    except FileExistsError as exc:
        print(exc)
        return 1
    except ValueError as exc:
        print(f"Not created: {exc}.")
        return 2
    if "PLATFORM_ADMIN_PASSWORD" not in os.environ:
        print(f"Password (shown once): {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
