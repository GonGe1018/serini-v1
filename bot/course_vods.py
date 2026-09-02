from datetime import datetime
from typing import Final, TypedDict

from schedule import TIMEZONE

COURSE_VODS_JS: Final = r"""
(courseId) => {
    var modules = new Map();
    var links = document.querySelectorAll('a[href*="/mod/vod/view.php"]');
    for (var i = 0; i < links.length; i++) {
        var link = links[i];
        var container = link.closest('.activityinstance');
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
                url: link.href
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


def _active_course_vod_events(
    modules: list[CourseVodModule],
    now: datetime,
) -> list[RawEvent]:
    events: list[RawEvent] = []
    seen_urls: set[str] = set()
    for module in modules:
        start = datetime.strptime(module["start"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=TIMEZONE
        )
        end = datetime.strptime(module["end"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=TIMEZONE
        )
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
