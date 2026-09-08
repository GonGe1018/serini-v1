from collections.abc import Awaitable, Callable
from typing import Final

from playwright.async_api import Page

from course_vods import RawEvent
from ecampus import ecampus_url

EXTRACURRICULAR_COURSE_IDS_JS: Final = r"""
() => Array.from(document.querySelectorAll('.course-box')).flatMap(box => {
    var badge = box.querySelector('.badge-course');
    if (!badge || badge.textContent.trim() !== '비교과') {
        return [];
    }
    var link = box.querySelector('a.course-link[href]');
    if (!link) {
        return [];
    }
    var url = new URL(link.href);
    if (url.origin !== window.location.origin || url.pathname !== '/course/view.php') {
        return [];
    }
    var courseId = url.searchParams.get('id');
    return courseId ? [courseId] : [];
})
"""

Navigate = Callable[[Page, str, str], Awaitable[None]]


async def extracurricular_course_ids(page: Page, navigate: Navigate) -> set[str]:
    await navigate(page, ecampus_url("/dashboard.php"), ".course-box")
    course_ids: list[str] = await page.evaluate(EXTRACURRICULAR_COURSE_IDS_JS)
    return set(course_ids)


def without_extracurricular_courses(
    course_map: dict[str, str],
    events: list[RawEvent],
    extracurricular_ids: set[str],
) -> tuple[dict[str, str], list[RawEvent]]:
    return (
        {
            course_id: name
            for course_id, name in course_map.items()
            if course_id not in extracurricular_ids
        },
        [
            event
            for event in events
            if event["courseId"] not in extracurricular_ids
        ],
    )
