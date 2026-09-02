import logging
from datetime import datetime
from typing import Literal, assert_never

from activity_status import normalize_activity_title as _normalize_activity_title
from config import bot_settings
from course_vods import RawEvent
from ecampus import ecampus_url
from ecampus_errors import EcampusLoginError, EcampusScrapeError
from embeds import EventData, EventItem
from event_enrichment import (
    append_active_course_vods,
    collect_completed_activity_urls,
    collect_completed_video_urls,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout
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
        var linkEl = el.querySelector('a[href*="/mod/"]');
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
    response = await page.goto(url, timeout=_TIMEOUT, wait_until="networkidle")
    if "login" in page.url:
        raise EcampusLoginError
    if response is None or not response.ok:
        raise EcampusScrapeError
    if await page.locator(expected_selector).count() == 0:
        raise EcampusScrapeError


def _partition_events(
    raw: list[RawEvent],
    course_map: dict[str, str],
    completed_urls: set[str],
) -> EventData:
    assignments: list[EventItem] = []
    quizzes: list[EventItem] = []
    videos: list[EventItem] = []
    completed_assignments: list[EventItem] = []
    completed_quizzes: list[EventItem] = []
    completed_videos: list[EventItem] = []

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
        is_completed = item["url"] in completed_urls
        match kind:
            case "assignment":
                (completed_assignments if is_completed else assignments).append(item)
            case "quiz":
                (completed_quizzes if is_completed else quizzes).append(item)
            case "video":
                (completed_videos if is_completed else videos).append(item)
            case unreachable:
                assert_never(unreachable)

    return {
        "assignments": assignments,
        "quizzes": quizzes,
        "videos": videos,
        "completed_assignments": completed_assignments,
        "completed_quizzes": completed_quizzes,
        "completed_videos": completed_videos,
    }


async def get_upcoming_events(ecampus_id: str, ecampus_pw: str) -> EventData:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            await page.goto(
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

            await _goto_authenticated(
                page,
                ecampus_url("/calendar/view.php?view=upcoming"),
                "select.cal_courses_flt",
            )

            course_map: dict[str, str] = await page.evaluate(_COURSE_MAP_JS)
            raw: list[RawEvent] = await page.evaluate(_SCRAPE_JS)

            now = datetime.now(TIMEZONE)
            await append_active_course_vods(
                page,
                course_map,
                raw,
                now,
                _goto_authenticated,
            )
            completed_urls = await collect_completed_video_urls(
                page,
                raw,
                _classify,
                _goto_authenticated,
            )
            completed_urls.update(
                await collect_completed_activity_urls(
                    page,
                    raw,
                    _classify,
                    _goto_authenticated,
                )
            )
        except EcampusLoginError:
            raise
        except PlaywrightTimeout as exc:
            logger.exception("ecampus 타임아웃 (id=%s)", ecampus_id)
            raise EcampusScrapeError from exc
        except PlaywrightError as exc:
            logger.exception("ecampus 스크래핑 실패 (id=%s)", ecampus_id)
            raise EcampusScrapeError from exc
        finally:
            await browser.close()

    return _partition_events(raw, course_map, completed_urls)
