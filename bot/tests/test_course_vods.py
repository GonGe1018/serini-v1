from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from playwright.async_api import async_playwright

from course_vods import COURSE_VODS_JS, CourseVodModule, _active_course_vod_events


def test_active_course_vod_events_includes_deadlines_outside_upcoming_horizon() -> None:
    modules: list[CourseVodModule] = [
        {
            "courseId": "31329",
            "title": "미적분학2 1주차 12-1",
            "start": "2026-09-01 00:00:00",
            "end": "2026-09-14 23:59:59",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=368252",
            "completed": True,
        },
        {
            "courseId": "31329",
            "title": "미적분학2 2주차 12-3",
            "start": "2026-09-08 00:00:00",
            "end": "2026-09-21 23:59:59",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=368256",
            "completed": False,
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


def test_course_vod_events_ignore_malformed_dates_and_external_urls() -> None:
    modules: list[CourseVodModule] = [
        {
            "courseId": "31329",
            "title": "잘못된 기간",
            "start": "2026-99-01 00:00:00",
            "end": "2026-09-14 23:59:59",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=bad-date",
            "completed": False,
        },
        {
            "courseId": "31329",
            "title": "외부 링크",
            "start": "2026-09-01 00:00:00",
            "end": "2026-09-14 23:59:59",
            "url": "https://attacker.example/mod/vod/view.php?id=external",
            "completed": False,
        },
    ]

    events = _active_course_vod_events(
        modules,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert events == []


@pytest.mark.asyncio
async def test_course_vod_completion_extraction_returns_booleans() -> None:
    html = """
    <div class="activity">
      <img title="완료함: 시청 완료">
      <div class="activityinstance">
        <a href="https://ecampus.sejong.ac.kr/mod/vod/view.php?id=done">완료 강의</a>
        <span>2026-09-01 00:00:00 ~ 2026-09-14 23:59:59</span>
      </div>
    </div>
    <div class="activity">
      <div class="activityinstance">
        <a href="https://ecampus.sejong.ac.kr/mod/vod/view.php?id=pending">미완료 강의</a>
        <span>2026-09-01 00:00:00 ~ 2026-09-14 23:59:59</span>
      </div>
    </div>
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.route(
                "https://ecampus.sejong.ac.kr/**",
                lambda route: route.fulfill(
                    body=html,
                    headers={"content-type": "text/html; charset=utf-8"},
                ),
            )
            await page.goto("https://ecampus.sejong.ac.kr/course/view.php?id=31329")
            modules: list[CourseVodModule] = await page.evaluate(
                COURSE_VODS_JS,
                "31329",
            )
        finally:
            await browser.close()

    assert [module["completed"] for module in modules] == [True, False]
