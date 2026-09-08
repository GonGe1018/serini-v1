import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Literal, TypedDict, assert_never

from bs4 import BeautifulSoup

from course_vods import RawEvent


class VodProgressRow(TypedDict):
    title: str
    completed: bool


_EVENT_DATE_PATTERN = re.compile(r"(?P<year>\d{4})년\s*0?(?P<month>\d{1,2})월\s*0?(?P<day>\d{1,2})일.*?(?:(?P<ampm_before>오전|오후)\s*(?P<hour_before>\d{1,2}):(?P<minute_before>\d{2})|(?P<hour_after>\d{1,2}):(?P<minute_after>\d{2})\s*(?P<ampm_after>오전|오후))")


def normalize_activity_title(title: str) -> str:
    return " ".join(title.replace("+", " ").split())


def normalize_event_date(value: str, reference: datetime | None = None) -> str:
    normalized = " ".join(value.split())
    match = _EVENT_DATE_PATTERN.search(normalized)
    if match is not None:
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
    elif reference is not None and normalized.startswith(("오늘", "내일")):
        relative_date = reference + timedelta(
            days=1 if normalized.startswith("내일") else 0
        )
        year, month, day = relative_date.year, relative_date.month, relative_date.day
        match = re.search(
            r"(?:(?P<ampm_before>오전|오후)\s*(?P<hour_before>\d{1,2}):(?P<minute_before>\d{2})|(?P<hour_after>\d{1,2}):(?P<minute_after>\d{2})\s*(?P<ampm_after>오전|오후))",
            normalized,
        )
    else:
        return normalized
    if match is None:
        return normalized
    ampm = match.group("ampm_before") or match.group("ampm_after")
    hour_text = match.group("hour_before") or match.group("hour_after")
    minute_text = match.group("minute_before") or match.group("minute_after")
    if ampm is None or hour_text is None or minute_text is None:
        return normalized
    hour = int(hour_text) % 12 + (12 if ampm == "오후" else 0)
    return (
        f"{year:04}-{month:02}-{day:02}T{hour:02}:{int(minute_text):02}"
    )


def _clean_video_title(title: str) -> str:
    cleaned = normalize_activity_title(
        title.removesuffix(" : Progress stop").removesuffix(" : Progress start")
    )
    if cleaned.endswith(".."):
        return cleaned[:-2].rstrip()
    return cleaned


def completed_video_urls(
    video_events: list[RawEvent],
    progress_rows: list[VodProgressRow],
) -> set[str]:
    event_titles = [_clean_video_title(event["title"]) for event in video_events]
    report_titles = [normalize_activity_title(row["title"]) for row in progress_rows]
    event_counts = Counter(event_titles)
    report_counts = Counter(report_titles)
    completed_counts = Counter(
        normalize_activity_title(row["title"])
        for row in progress_rows
        if row["completed"]
    )

    completed_urls: set[str] = set()
    for event, title in zip(video_events, event_titles, strict=True):
        if (
            event["url"]
            and event_counts[title] == report_counts[title]
            and completed_counts[title] == report_counts[title]
        ):
            completed_urls.add(event["url"])
    return completed_urls


def activity_is_completed(kind: Literal["assignment", "quiz"], html: str) -> bool:
    document = BeautifulSoup(html, "html.parser")
    match kind:
        case "quiz":
            for row in document.select(".quizattemptsummary tbody tr"):
                if row.select_one('a[href*="/mod/quiz/review.php"]') is not None:
                    return True
                state_cell = row.select_one(".state")
                state = (
                    normalize_activity_title(state_cell.get_text(" ", strip=True)).lower()
                    if state_cell is not None
                    else ""
                )
                if state in {"종료됨", "제출됨", "finished", "submitted"}:
                    return True
            return False
        case "assignment":
            return document.select_one(
                ".submissionstatussubmitted, .submissionstatusgraded"
            ) is not None
        case unreachable:
            assert_never(unreachable)
