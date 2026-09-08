import pytest
from playwright.async_api import async_playwright

from course_catalog import (
    EXTRACURRICULAR_COURSE_IDS_JS,
    without_extracurricular_courses,
)
from course_vods import RawEvent


@pytest.mark.asyncio
async def test_extracurricular_course_ids_come_from_labeled_course_cards() -> None:
    # Given
    html = """
    <div class="course-box">
      <a class="course-link" href="/course/view.php?id=31057">
        <span class="badge-course">비교과</span>
        <span>의무교육</span>
      </a>
    </div>
    <div class="course-box">
      <a class="course-link" href="/course/view.php?id=31329">
        <span class="badge-course">교과</span>
        <span>미적분학2</span>
      </a>
    </div>
    <div class="course-box">
      <a class="course-link" href="https://attacker.example/course/view.php?id=99999">
        <span class="badge-course">비교과</span>
        <span>외부 강좌</span>
      </a>
    </div>
    """

    # When
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
            await page.goto("https://ecampus.sejong.ac.kr/dashboard.php")
            course_ids: list[str] = await page.evaluate(
                EXTRACURRICULAR_COURSE_IDS_JS
            )
        finally:
            await browser.close()

    # Then
    assert course_ids == ["31057"]


def test_without_extracurricular_courses_keeps_only_regular_course_data() -> None:
    # Given
    course_map = {"31057": "의무교육", "31329": "미적분학2"}
    events: list[RawEvent] = [
        {
            "courseId": "31057",
            "title": "예방교육 : Progress stop",
            "date": "2026년 11월 30일, 오후 11:59",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=330831",
        },
        {
            "courseId": "31329",
            "title": "미적분학2 : Progress stop",
            "date": "2026년 9월 14일, 오후 11:59",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=368252",
        },
    ]

    # When
    regular_course_map, regular_events = without_extracurricular_courses(
        course_map,
        events,
        {"31057"},
    )

    # Then
    assert regular_course_map == {"31329": "미적분학2"}
    assert [event["courseId"] for event in regular_events] == ["31329"]
