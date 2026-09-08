import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypedDict
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from activity_status import activity_is_completed
from course_vods import RawEvent
from ecampus import is_ecampus_url
from schedule import TIMEZONE

COURSE_ACTIVITY_LINKS_JS: Final = r"""
() => Array.from(new Map(Array.from(document.querySelectorAll(
    'a[href*="/mod/quiz/view.php"], a[href*="/mod/assign/view.php"]'
)).filter(link => new URL(link.href).origin === window.location.origin).map(link => [link.href, {
    title: link.innerText.trim().split('\n')[0],
    url: link.href
}])).values())
"""

_DATE_VALUE: Final = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
_START_PATTERNS: Final = (
    re.compile(rf"시작\s*일시\s*:\s*{_DATE_VALUE}"),
    re.compile(rf"제출\s*시작\s*:\s*{_DATE_VALUE}"),
    re.compile(rf"{_DATE_VALUE}\s*까지는\s*퀴즈를\s*이용할\s*수\s*없음"),
)
_END_PATTERN: Final = re.compile(
    rf"(?:종료\s*일시|제출\s*종료|마감\s*일시)\s*:\s*{_DATE_VALUE}"
)
_ACTIVITY_PATHS: Final = frozenset(
    {"/mod/assign/view.php", "/mod/quiz/view.php"}
)


class CourseActivityLink(TypedDict):
    title: str
    url: str


class CourseActivityModule(CourseActivityLink):
    courseId: str


@dataclass(frozen=True, slots=True)
class ActiveCourseActivity:
    event: RawEvent
    completed: bool


def is_course_activity_url(url: str) -> bool:
    return is_ecampus_url(url) and urlsplit(url).path in _ACTIVITY_PATHS


def _activity_period(html: str) -> tuple[datetime | None, datetime] | None:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    end_match = _END_PATTERN.search(text)
    if end_match is None:
        return None
    try:
        end = datetime.strptime(end_match.group(1), "%Y-%m-%d %H:%M").replace(
            tzinfo=TIMEZONE
        )
        start = next(
            (
                datetime.strptime(match.group(1), "%Y-%m-%d %H:%M").replace(
                    tzinfo=TIMEZONE
                )
                for pattern in _START_PATTERNS
                if (match := pattern.search(text)) is not None
            ),
            None,
        )
    except ValueError:
        return None
    return start, end


def course_activity_is_inactive(html: str, now: datetime) -> bool:
    period = _activity_period(html)
    if period is None:
        return False
    start, end = period
    return (start is not None and now < start) or now > end


def active_course_activity(
    module: CourseActivityModule,
    html: str,
    now: datetime,
) -> ActiveCourseActivity | None:
    url = module["url"]
    if not is_course_activity_url(url):
        return None
    kind: Literal["assignment", "quiz"]
    if "/mod/assign/" in url:
        kind = "assignment"
    elif "/mod/quiz/" in url:
        kind = "quiz"
    else:
        return None

    period = _activity_period(html)
    if period is None:
        return None
    start, end = period
    if (start is not None and now < start) or now > end:
        return None

    period = "오전" if end.hour < 12 else "오후"
    hour = end.hour % 12 or 12
    title = f"{module['title']} closes" if kind == "quiz" else "마감 기한"
    return ActiveCourseActivity(
        event={
            "courseId": module["courseId"],
            "title": title,
            "date": (
                f"{end.year}년 {end.month}월 {end.day}일, "
                f"{period} {hour}:{end.minute:02d}"
            ),
            "desc": module["title"] if kind == "assignment" else "",
            "url": url,
        },
        completed=activity_is_completed(kind, html),
    )
