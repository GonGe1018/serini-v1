from datetime import datetime
from zoneinfo import ZoneInfo

from course_vods import CourseVodModule, _active_course_vod_events


def test_active_course_vod_events_includes_deadlines_outside_upcoming_horizon() -> None:
    modules: list[CourseVodModule] = [
        {
            "courseId": "31329",
            "title": "미적분학2 1주차 12-1",
            "start": "2026-09-01 00:00:00",
            "end": "2026-09-14 23:59:59",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=368252",
        },
        {
            "courseId": "31329",
            "title": "미적분학2 2주차 12-3",
            "start": "2026-09-08 00:00:00",
            "end": "2026-09-21 23:59:59",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=368256",
        },
    ]

    events = _active_course_vod_events(
        modules,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert [event["title"] for event in events] == [
        "미적분학2 1주차 12-1 : Progress stop"
    ]
    assert events[0]["date"] == "2026년 9월 14일, 오후 11:59"
