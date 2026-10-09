"""Check the books against themselves. Used after every restore drill and before go-live.

    python -m app.scripts.verify          # quick
    python -m app.scripts.verify --full   # also re-reads every stored file

Exit code 0 when nothing failed, 1 otherwise."""

import sys

from app import services as _services  # noqa: F401 - registers audit listeners
from app.core.db import SessionLocal
from app.services import verify


def main(argv: list[str]) -> int:
    with SessionLocal() as db:
        result = verify.run_checks(db, full="--full" in argv)
    for c in result.checks:
        print(f"[{c.state.upper():4}] {c.name}: {c.detail}")
    print("OK" if result.ok else "FAILED")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
