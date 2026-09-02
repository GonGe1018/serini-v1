from collections import Counter
from typing import Literal, TypedDict, assert_never

from bs4 import BeautifulSoup
from course_vods import RawEvent


class VodProgressRow(TypedDict):
    title: str
    completed: bool


def normalize_activity_title(title: str) -> str:
    return " ".join(title.replace("+", " ").split())


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
