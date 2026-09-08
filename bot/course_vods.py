from datetime import datetime
from typing import Final, TypedDict
from urllib.parse import urlsplit

from ecampus import is_ecampus_url
from schedule import TIMEZONE

COURSE_VODS_JS: Final = r"""
(courseId) => {
    var modules = new Map();
    var links = Array.from(document.querySelectorAll('a[href]')).filter(link => {
        var url = new URL(link.href);
        return url.origin === window.location.origin &&
            url.pathname === '/mod/vod/view.php';
    });
    for (var i = 0; i < links.length; i++) {
        var link = links[i];
        var container = link.closest('.activityinstance');
        var activity = link.closest('.activity');
        var text = container ? container.innerText : '';
        var period = text.match(
            /(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*~\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/
        );
        if (period) {
            modules.set(link.href, {
                courseId: courseId,
                title: link.innerText.trim().split('\n')[0],
                start: period[1],
                end: period[2],
                url: link.href,
                completed: Boolean(activity && activity.querySelector(
                    'img[title^="완료함:"], img[alt^="완료함:"]'
                ))
            });
        }
    }
    return Array.from(modules.values());
}
"""


class RawEvent(TypedDict):
    courseId: str
    title: str
    date: str
    desc: str
    url: str


class CourseVodModule(TypedDict):
    courseId: str
    title: str
    start: str
    end: str
    url: str
    completed: bool


def is_course_vod_url(url: str) -> bool:
    return is_ecampus_url(url) and urlsplit(url).path == "/mod/vod/view.php"


def _course_vod_period(
    module: CourseVodModule,
) -> tuple[datetime, datetime] | None:
    if not is_course_vod_url(module["url"]):
        return None
    try:
        start = datetime.strptime(
            module["start"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=TIMEZONE)
        end = datetime.strptime(module["end"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=TIMEZONE
        )
    except ValueError:
        return None
    return start, end


def inactive_course_vod_urls(
    modules: list[CourseVodModule],
    now: datetime,
) -> set[str]:
    inactive_urls: set[str] = set()
    for module in modules:
        period = _course_vod_period(module)
        if period is not None and not period[0] <= now <= period[1]:
            inactive_urls.add(module["url"])
    return inactive_urls


def _active_course_vod_events(
    modules: list[CourseVodModule],
    now: datetime,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    seen_urls: set[str] = set()
    for module in modules:
        period = _course_vod_period(module)
        if period is None:
            continue
        start, end = period
        if module["url"] in seen_urls or not start <= now <= end:
            continue
        seen_urls.add(module["url"])
        period = "오전" if end.hour < 12 else "오후"
        hour = end.hour % 12 or 12
        events.append(
            {
                "courseId": module["courseId"],
                "title": f"{module['title']} : Progress stop",
                "date": (
                    f"{end.year}년 {end.month}월 {end.day}일, "
                    f"{period} {hour}:{end.minute:02d}"
                ),
                "desc": "",
                "url": module["url"],
            }
        )
    return events
