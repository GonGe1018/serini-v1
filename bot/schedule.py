from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

from config import bot_settings

ScheduleTime = tuple[int, int]


def parse_report_schedule(value: str) -> tuple[ScheduleTime, ...]:
    parsed: list[ScheduleTime] = []
    for entry in value.split(","):
        hour, minute = entry.split(":")
        parsed.append((int(hour), int(minute)))
    return tuple(sorted(parsed))


REPORT_TIMES: Final = parse_report_schedule(bot_settings.report_schedule)
REPORT_SCHEDULE_TEXT: Final = " / ".join(
    f"{hour:02d}:{minute:02d}" for hour, minute in REPORT_TIMES
)
TIMEZONE: Final = ZoneInfo(bot_settings.timezone)


def next_report_time(now: datetime | None = None) -> str:
    current = datetime.now(TIMEZONE) if now is None else now.astimezone(TIMEZONE)
    for hour, minute in REPORT_TIMES:
        scheduled = current.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        if scheduled > current:
            return scheduled.strftime("%H:%M")
    first_hour, first_minute = REPORT_TIMES[0]
    return f"내일 {first_hour:02d}:{first_minute:02d}"
