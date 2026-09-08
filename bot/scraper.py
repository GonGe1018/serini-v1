import logging
from datetime import datetime
from threading import BoundedSemaphore, Lock
from typing import Literal

import anyio
from playwright.async_api import (
    Browser,
    Page,
    Playwright,
    Request,
    Route,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from activity_status import normalize_activity_title as _normalize_activity_title
from activity_status import normalize_event_date
from config import bot_settings
from course_catalog import (
    extracurricular_course_ids,
    without_extracurricular_courses,
)
from course_vods import RawEvent
from ecampus import ecampus_url, is_ecampus_url
from ecampus_errors import EcampusLoginError, EcampusScrapeError
from embeds import EventData, EventItem
from event_enrichment import (
    collect_completed_video_urls,
    enrich_active_course_events,
)
from schedule import TIMEZONE

logger = logging.getLogger(__name__)

EventKind = Literal["assignment", "quiz", "video", "other"]


_SCRAPE_JS = """
() => {
    var events = [];
    var els = document.querySelectorAll('.event');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var titleEl = el.querySelector('h3.name');
        var dateEl = el.querySelector('.calendar-date');
        var descEl = el.querySelector('.calendar-body');
        var linkEl = Array.from(el.querySelectorAll('a[href]')).find(link => {
            var url = new URL(link.href);
            return url.origin === window.location.origin && [
                '/mod/assign/view.php',
                '/mod/quiz/view.php',
                '/mod/vod/view.php'
            ].includes(url.pathname);
        });
        events.push({
            courseId: el.getAttribute('data-course-id') || '',
            title: titleEl ? titleEl.textContent.trim() : '',
            date: dateEl ? dateEl.textContent.trim() : '',
            desc: descEl ? descEl.innerText.trim().substring(0, 200) : '',
            url: linkEl ? linkEl.href : ''
        });
    }
    return events;
}
"""

_COURSE_MAP_JS = """
() => {
    var map = {};
    var opts = document.querySelectorAll('select.cal_courses_flt option');
    for (var i = 0; i < opts.length; i++) {
        var val = opts[i].value;
        var text = opts[i].textContent.trim();
        if (val && val !== '1') {
            var name = text.replace(/\\s*\\(\\S+\\)\\s*$/, '').trim();
            map[val] = name;
        }
    }
    return map;
}
"""

_TIMEOUT = bot_settings.ecampus_timeout_ms
_SCRAPE_TIMEOUT_SECONDS = 90
_MAX_CONCURRENT_SCRAPES = 2
_SCRAPE_SLOTS = BoundedSemaphore(_MAX_CONCURRENT_SCRAPES)
_ACTIVE_SCRAPE_IDS: set[str] = set()
_ACTIVE_SCRAPE_IDS_LOCK = Lock()


def _acquire_scrape_slot(ecampus_id: str) -> bool:
    with _ACTIVE_SCRAPE_IDS_LOCK:
        if ecampus_id in _ACTIVE_SCRAPE_IDS:
            return False
        if not _SCRAPE_SLOTS.acquire(blocking=False):
            return False
        _ACTIVE_SCRAPE_IDS.add(ecampus_id)
        return True


def _release_scrape_slot(ecampus_id: str) -> None:
    with _ACTIVE_SCRAPE_IDS_LOCK:
        _ACTIVE_SCRAPE_IDS.remove(ecampus_id)
        _SCRAPE_SLOTS.release()


def _classify(title: str) -> EventKind:
    t = title.lower()
    if "progress stop" in t:
        return "video"
    if "closes" in t or "퀴즈" in t:
        return "quiz"
    if title == "마감 기한":
        return "assignment"
    return "other"


def _clean_title(title: str, desc: str) -> str:
    if title == "마감 기한":
        first_line = desc.split("\n")[0].strip() if desc else ""
        return first_line or "과제 제출"
    for suffix in (" : Progress stop", " : Progress start"):
        title = title.removesuffix(suffix)
    title = title.removesuffix(" closes")
    title = _normalize_activity_title(title)
    if title.endswith(".."):
        title = title[:-2].rstrip()
    return title


async def _goto_authenticated(
    page: Page,
    url: str,
    expected_selector: str,
) -> None:
    if not is_ecampus_url(url):
        raise EcampusScrapeError
    response = await page.goto(url, timeout=_TIMEOUT, wait_until="networkidle")
    if "login" in page.url:
        raise EcampusLoginError
    if not is_ecampus_url(page.url) or response is None or not response.ok:
        raise EcampusScrapeError
    if await page.locator(expected_selector).count() == 0:
        raise EcampusScrapeError


async def _route_ecampus_navigation(route: Route, request: Request) -> None:
    if not is_ecampus_url(request.url):
        await route.abort()
        return
    await route.continue_()


def _partition_events(
    raw: list[RawEvent],
    course_map: dict[str, str],
    completed_urls: set[str],
    now: datetime | None = None,
) -> EventData:
    assignments: list[EventItem] = []
    quizzes: list[EventItem] = []
    videos: list[EventItem] = []
    completed_assignments: list[EventItem] = []
    completed_quizzes: list[EventItem] = []
    completed_videos: list[EventItem] = []
    reference = datetime.now(TIMEZONE) if now is None else now
    prepared_events: list[
        tuple[tuple[str, str, str, str], EventKind, EventItem]
    ] = []
    urls_by_identity: dict[tuple[str, str, str, str], set[str]] = {}

    for event in raw:
        kind = _classify(event["title"])
        if kind == "other":
            continue
        course = course_map.get(
            event["courseId"],
            f"과목({event['courseId'] or '?'})",
        )
        item: EventItem = {
            "course": course,
            "title": _clean_title(event["title"], event["desc"]),
            "date": event["date"].strip(),
            "desc": (
                event["desc"].split("\n")[0].strip()
                if kind != "assignment"
                else ""
            ),
            "url": event["url"],
        }
        identity = (
            event["courseId"],
            kind,
            item["title"],
            normalize_event_date(item["date"], reference),
        )
        prepared_events.append((identity, kind, item))
        if item["url"]:
            urls_by_identity.setdefault(identity, set()).add(item["url"])

    selected_events: list[tuple[EventKind, EventItem]] = []
    seen_entries: set[tuple[tuple[str, str, str, str], str]] = set()
    for identity, kind, item in prepared_events:
        urls = urls_by_identity.get(identity, set())
        if urls and not item["url"]:
            continue
        entry_key = (identity, item["url"])
        if entry_key in seen_entries:
            continue
        seen_entries.add(entry_key)
        selected_events.append((kind, item))

    for kind, item in selected_events:
        is_completed = item["url"] in completed_urls
        match kind:
            case "assignment":
                (completed_assignments if is_completed else assignments).append(item)
            case "quiz":
                (completed_quizzes if is_completed else quizzes).append(item)
            case "video":
                (completed_videos if is_completed else videos).append(item)
            case "other":
                continue

    return {
        "assignments": assignments,
        "quizzes": quizzes,
        "videos": videos,
        "completed_assignments": completed_assignments,
        "completed_quizzes": completed_quizzes,
        "completed_videos": completed_videos,
    }


async def _collect_upcoming_events(
    page: Page,
    ecampus_id: str,
    ecampus_pw: str,
) -> EventData:
    _ = await page.route("**/*", _route_ecampus_navigation)
    _ = await page.goto(
        ecampus_url("/login/index.php"),
        timeout=_TIMEOUT,
        wait_until="networkidle",
    )
    await page.locator('input[name="username"]').first.fill(ecampus_id)
    await page.locator('input[name="password"]').first.fill(ecampus_pw)
    await page.locator('input[name="loginbutton"]').first.click()
    await page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

    if "login" in page.url:
        logger.warning("ecampus 로그인 실패 (id=%s)", ecampus_id)
        raise EcampusLoginError

    extracurricular_ids = await extracurricular_course_ids(
        page,
        _goto_authenticated,
    )
    await _goto_authenticated(
        page,
        ecampus_url("/calendar/view.php?view=upcoming"),
        "select.cal_courses_flt",
    )

    course_map: dict[str, str] = await page.evaluate(_COURSE_MAP_JS)
    raw: list[RawEvent] = await page.evaluate(_SCRAPE_JS)
    course_map, raw = without_extracurricular_courses(
        course_map,
        raw,
        extracurricular_ids,
    )
    now = datetime.now(TIMEZONE)
    completed_urls = await enrich_active_course_events(
        page,
        course_map,
        raw,
        now,
        _goto_authenticated,
    )
    completed_urls.update(
        await collect_completed_video_urls(
            page,
            raw,
            _classify,
            _goto_authenticated,
        )
    )
    return _partition_events(raw, course_map, completed_urls, now)


async def _scrape_upcoming_events(ecampus_id: str, ecampus_pw: str) -> EventData:
    playwright: Playwright | None = None
    browser: Browser | None = None
    try:
        with anyio.fail_after(_SCRAPE_TIMEOUT_SECONDS):
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            return await _collect_upcoming_events(page, ecampus_id, ecampus_pw)
    except EcampusLoginError:
        raise
    except PlaywrightTimeout as exc:
        logger.exception("ecampus 타임아웃 (id=%s)", ecampus_id)
        raise EcampusScrapeError from exc
    except PlaywrightError as exc:
        logger.exception("ecampus 스크래핑 실패 (id=%s)", ecampus_id)
        raise EcampusScrapeError from exc
    except TimeoutError as exc:
        logger.exception("ecampus 전체 수집 시간 초과 (id=%s)", ecampus_id)
        raise EcampusScrapeError from exc
    finally:
        if browser is not None:
            with anyio.move_on_after(5, shield=True):
                try:
                    await browser.close()
                except PlaywrightError as error:
                    _log_cleanup_failure("browser", error)
        if playwright is not None:
            with anyio.move_on_after(5, shield=True):
                try:
                    await playwright.stop()
                except PlaywrightError as error:
                    _log_cleanup_failure("playwright", error)


def _log_cleanup_failure(resource: str, error: PlaywrightError) -> None:
    logger.warning("ecampus %s 정리 실패: %s", resource, error)


async def get_upcoming_events(ecampus_id: str, ecampus_pw: str) -> EventData:
    if not _acquire_scrape_slot(ecampus_id):
        raise EcampusScrapeError
    try:
        return await _scrape_upcoming_events(ecampus_id, ecampus_pw)
    finally:
        _release_scrape_slot(ecampus_id)
