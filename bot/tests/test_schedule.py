from datetime import datetime
from zoneinfo import ZoneInfo

from ecampus import ecampus_url
from schedule import (
    REPORT_SCHEDULE_TEXT,
    REPORT_TIMES,
    next_report_time,
    parse_report_schedule,
)


def test_report_schedule_defaults_match_existing_delivery_times() -> None:
    assert REPORT_TIMES == ((8, 0), (13, 0), (21, 0))
    assert REPORT_SCHEDULE_TEXT == "08:00 / 13:00 / 21:00"


def test_parse_report_schedule_supports_operational_override() -> None:
    assert parse_report_schedule("07:30,19:45") == ((7, 30), (19, 45))


def test_parse_report_schedule_orders_overridden_times() -> None:
    assert parse_report_schedule("19:45,07:30") == ((7, 30), (19, 45))


def test_ecampus_url_uses_configured_base_url() -> None:
    assert ecampus_url("/calendar/view.php?view=upcoming") == (
        "https://ecampus.sejong.ac.kr/calendar/view.php?view=upcoming"
    )


def test_next_report_time_uses_configured_timezone_and_rolls_to_tomorrow() -> None:
    timezone = ZoneInfo("Asia/Seoul")

    assert next_report_time(datetime(2026, 9, 2, 12, 0, tzinfo=timezone)) == "13:00"
    assert (
        next_report_time(datetime(2026, 9, 2, 22, 0, tzinfo=timezone))
        == "내일 08:00"
    )
