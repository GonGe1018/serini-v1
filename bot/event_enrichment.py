import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import Literal

from activity_status import (
    VodProgressRow,
    activity_is_completed,
    completed_video_urls,
)
from course_vods import (
    COURSE_VODS_JS,
    CourseVodModule,
    RawEvent,
    _active_course_vod_events,
)
from ecampus import ecampus_url
from ecampus_errors import EcampusLoginError, EcampusScrapeError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

logger = logging.getLogger(__name__)

EventKind = Literal["assignment", "quiz", "video", "other"]
Navigate = Callable[[Page, str, str], Awaitable[None]]
Classify = Callable[[str], EventKind]

_VOD_PROGRESS_JS = """
() => {
    var progress = [];
    var rows = document.querySelectorAll('tr');
    for (var i = 0; i < rows.length; i++) {
        var cells = rows[i].querySelectorAll('td');
        if (cells.length >= 6 && /^\\d+$/.test(cells[0].innerText.trim())) {
            progress.push({
                title: cells[1].innerText.trim(),
                completed: cells[4].innerText.trim() === 'O'
            });
        }
    }
    return progress;
}
"""


def _log_optional_failure(
    scope: str,
    identifier: str,
    error: Exception,
) -> None:
    logger.warning(
        "ecampus 선택 수집 실패 (%s=%s): %s",
        scope,
        identifier,
        error,
    )


async def append_active_course_vods(
    page: Page,
    course_ids: Iterable[str],
    raw: list[RawEvent],
    now: datetime,
    navigate: Navigate,
) -> None:
    event_urls = {event["url"] for event in raw if event["url"]}
    for course_id in course_ids:
        try:
            await navigate(
                page,
                ecampus_url(f"/course/view.php?id={course_id}"),
                f"body.course-{course_id}",
            )
            modules: list[CourseVodModule] = await page.evaluate(
                COURSE_VODS_JS,
                course_id,
            )
        except EcampusLoginError:
            raise
        except (EcampusScrapeError, PlaywrightError) as error:
            _log_optional_failure("course", course_id, error)
            continue

        for event in _active_course_vod_events(modules, now):
            if event["url"] not in event_urls:
                raw.append(event)
                event_urls.add(event["url"])


async def collect_completed_video_urls(
    page: Page,
    raw: list[RawEvent],
    classify: Classify,
    navigate: Navigate,
) -> set[str]:
    events_by_course: dict[str, list[RawEvent]] = {}
    for event in raw:
        course_id = event["courseId"]
        if classify(event["title"]) == "video" and course_id:
            events_by_course.setdefault(course_id, []).append(event)

    completed_urls: set[str] = set()
    for course_id, video_events in events_by_course.items():
        try:
            await navigate(
                page,
                ecampus_url(f"/report/ubcompletion/progress.php?id={course_id}"),
                "th",
            )
            rows: list[VodProgressRow] = await page.evaluate(_VOD_PROGRESS_JS)
        except EcampusLoginError:
            raise
        except (EcampusScrapeError, PlaywrightError) as error:
            _log_optional_failure("progress", course_id, error)
            continue
        completed_urls.update(completed_video_urls(video_events, rows))
    return completed_urls


async def collect_completed_activity_urls(
    page: Page,
    raw: list[RawEvent],
    classify: Classify,
    navigate: Navigate,
) -> set[str]:
    completed_urls: set[str] = set()
    for event in raw:
        kind = classify(event["title"])
        url = event["url"]
        if not url:
            continue
        if kind == "assignment":
            expected_selector = "body.path-mod-assign"
        elif kind == "quiz":
            expected_selector = "body.path-mod-quiz"
        else:
            continue
        try:
            await navigate(page, url, expected_selector)
            html = await page.content()
        except EcampusLoginError:
            raise
        except (EcampusScrapeError, PlaywrightError) as error:
            _log_optional_failure("activity", url, error)
            continue
        if activity_is_completed(kind, html):
            completed_urls.add(url)
    return completed_urls
