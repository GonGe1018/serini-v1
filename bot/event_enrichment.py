import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from itertools import batched
from typing import Final, Literal

import anyio
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

from activity_status import (
    VodProgressRow,
    completed_video_urls,
    normalize_activity_title,
    normalize_event_date,
)
from course_activities import (
    COURSE_ACTIVITY_LINKS_JS,
    ActiveCourseActivity,
    CourseActivityLink,
    CourseActivityModule,
    active_course_activity,
    course_activity_is_inactive,
    is_course_activity_url,
)
from course_vods import (
    COURSE_VODS_JS,
    CourseVodModule,
    RawEvent,
    _active_course_vod_events,
    inactive_course_vod_urls,
)
from ecampus import ecampus_url
from ecampus_errors import EcampusLoginError, EcampusScrapeError

logger = logging.getLogger(__name__)

EventKind = Literal["assignment", "quiz", "video", "other"]
Navigate = Callable[[Page, str, str], Awaitable[None]]
Classify = Callable[[str], EventKind]
_ACTIVITY_REQUEST_CONCURRENCY: Final = 4
_ACTIVITY_REQUEST_TIMEOUT_MS: Final = 5_000

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


async def _fetch_activity_html(page: Page, url: str) -> str:
    if not is_course_activity_url(url):
        raise EcampusScrapeError
    response = await page.request.get(
        url,
        timeout=_ACTIVITY_REQUEST_TIMEOUT_MS,
        max_redirects=0,
    )
    try:
        if 300 <= response.status < 400:
            if "login" in response.headers.get("location", ""):
                raise EcampusLoginError
            raise EcampusScrapeError
        if not response.ok or not is_course_activity_url(response.url):
            raise EcampusScrapeError
        return await response.text()
    finally:
        await response.dispose()


def _event_activity_title(event: RawEvent) -> str:
    source_title = (
        event["desc"].split("\n", maxsplit=1)[0]
        if event["title"] == "마감 기한"
        else event["title"].removesuffix(" closes")
    )
    return normalize_activity_title(source_title)


async def _inspect_activity_modules(
    page: Page,
    modules: Iterable[CourseActivityModule],
    now: datetime,
) -> tuple[dict[str, ActiveCourseActivity | None], set[str]]:
    results: dict[str, ActiveCourseActivity | None] = {}
    inactive_urls: set[str] = set()
    login_errors: list[EcampusLoginError] = []

    async def inspect(module: CourseActivityModule) -> None:
        try:
            html = await _fetch_activity_html(page, module["url"])
        except EcampusLoginError as error:
            login_errors.append(error)
        except (EcampusScrapeError, PlaywrightError) as error:
            _log_optional_failure("activity", module["url"], error)
        else:
            activity = active_course_activity(module, html, now)
            results[module["url"]] = activity
            if activity is None and course_activity_is_inactive(html, now):
                inactive_urls.add(module["url"])

    for batch in batched(modules, _ACTIVITY_REQUEST_CONCURRENCY):
        async with anyio.create_task_group() as task_group:
            for module in batch:
                _ = task_group.start_soon(inspect, module)
        if login_errors:
            raise login_errors[0]
    return results, inactive_urls


async def enrich_active_course_events(
    page: Page,
    course_ids: Iterable[str],
    raw: list[RawEvent],
    now: datetime,
    navigate: Navigate,
) -> set[str]:
    event_urls = {event["url"] for event in raw if event["url"]}
    completed_urls: set[str] = set()
    activity_modules: dict[str, CourseActivityModule] = {}
    for event in raw:
        if is_course_activity_url(event["url"]):
            activity_modules[event["url"]] = {
                "courseId": event["courseId"],
                "title": _event_activity_title(event),
                "url": event["url"],
            }

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
            activity_links: list[CourseActivityLink] = await page.evaluate(
                COURSE_ACTIVITY_LINKS_JS
            )
        except EcampusLoginError:
            raise
        except (EcampusScrapeError, PlaywrightError) as error:
            _log_optional_failure("course", course_id, error)
            continue

        for link in activity_links:
            if not is_course_activity_url(link["url"]):
                continue
            module: CourseActivityModule = {
                "courseId": course_id,
                "title": link["title"],
                "url": link["url"],
            }
            _ = activity_modules.setdefault(module["url"], module)

        inactive_vods = inactive_course_vod_urls(modules, now)
        raw[:] = [event for event in raw if event["url"] not in inactive_vods]
        for event in _active_course_vod_events(modules, now):
            candidates = [
                candidate
                for candidate in raw
                if candidate["courseId"] == event["courseId"]
                and candidate["title"] == event["title"]
                and not candidate["url"]
            ]
            exact_candidates = [
                candidate
                for candidate in candidates
                if normalize_event_date(candidate["date"], now)
                == normalize_event_date(event["date"], now)
            ]
            calendar_event = (
                exact_candidates[0]
                if len(exact_candidates) == 1
                else candidates[0]
                if len(candidates) == 1
                else None
            )
            if calendar_event is not None:
                calendar_event.update(event)
                event_urls.add(event["url"])
            elif event["url"] not in event_urls:
                raw.append(event)
                event_urls.add(event["url"])
        completed_urls.update(
            module["url"] for module in modules if module["completed"]
        )

    activities, inactive_urls = await _inspect_activity_modules(
        page,
        activity_modules.values(),
        now,
    )
    raw[:] = [event for event in raw if event["url"] not in inactive_urls]
    for module in activity_modules.values():
        activity = activities.get(module["url"])
        if activity is None:
            continue
        blank_candidates = [
            event
            for event in raw
            if event["courseId"] == module["courseId"]
            and not event["url"]
            and _event_activity_title(event)
            == normalize_activity_title(module["title"])
        ]
        exact_candidates = [
            event
            for event in blank_candidates
            if normalize_event_date(event["date"], now)
            == normalize_event_date(activity.event["date"], now)
        ]
        dated_candidates = [
            event
            for event in raw
            if event["courseId"] == module["courseId"]
            and not event["url"]
            and event["title"] == activity.event["title"]
            and normalize_event_date(event["date"], now)
            == normalize_event_date(activity.event["date"], now)
        ]
        calendar_event = (
            exact_candidates[0]
            if len(exact_candidates) == 1
            else blank_candidates[0]
            if len(blank_candidates) == 1
            else dated_candidates[0]
            if len(dated_candidates) == 1
            else None
        )
        if calendar_event is not None:
            if _event_activity_title(calendar_event) != normalize_activity_title(
                module["title"]
            ):
                calendar_event["desc"] = activity.event["desc"]
            calendar_event["url"] = module["url"]
            event_urls.add(module["url"])
        elif module["url"] not in event_urls:
            raw.append(activity.event)
            event_urls.add(module["url"])
        if activity.completed:
            completed_urls.add(module["url"])
    return completed_urls


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
