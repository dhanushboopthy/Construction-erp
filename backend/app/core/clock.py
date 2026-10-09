"""The only place that reads the clock. Services take `today` from here and pass it to domain
functions, which never read the clock themselves."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

SHOP_TZ = ZoneInfo("Asia/Kolkata")


def now_utc() -> datetime:
    return datetime.now(UTC)


def today_ist() -> date:
    return datetime.now(SHOP_TZ).date()
