"""What scripts/backup-loop.sh asks the application (Milestone 25).

    python -m app.scripts.backup_schedule time            # nightly time as HHMM, container clock
    python -m app.scripts.backup_schedule start           # note a run; prints: <id> <dump> <files>
    python -m app.scripts.backup_schedule finish <id> ok  # or: finish <id> failed "why"
    python -m app.scripts.backup_schedule prune           # delete copies the schedule drops

The schedule lives in the `platform_backup_schedule` row the admin edits. Exit code 0 on
success, 1 otherwise."""

import sys
from datetime import datetime

from app import services as _services  # noqa: F401 - registers listeners
from app.core.clock import SHOP_TZ
from app.core.db import SessionLocal
from app.domain import backups as rules
from app.services.platform import backups as service


def _time_text(db_time: str) -> str:
    """The shop-time schedule as the container's own HHMM (the loop reads `date +%H%M`)."""
    at = rules.parse_daily_time(db_time)
    local = datetime.now(SHOP_TZ).replace(hour=at.hour, minute=at.minute).astimezone()
    return local.strftime("%H%M")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    command, rest = argv[0], argv[1:]
    with SessionLocal() as db:
        if command == "time":
            print(_time_text(service.schedule_row(db).daily_time))
        elif command == "start":
            backup_id, dump, files = service.record_scheduled_start(db, datetime.now().astimezone())
            print(backup_id, dump, files)
        elif command == "finish" and len(rest) >= 2 and rest[0].isdigit():
            error = " ".join(rest[2:]) or None
            service.record_scheduled_finish(db, int(rest[0]), rest[1] == "ok", error)
        elif command == "prune":
            print(service.prune(db))
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
