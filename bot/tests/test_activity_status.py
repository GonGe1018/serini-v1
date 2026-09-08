from datetime import datetime
from zoneinfo import ZoneInfo

from activity_status import (
    VodProgressRow,
    activity_is_completed,
    completed_video_urls,
    normalize_event_date,
)
from course_vods import RawEvent


def test_completed_video_urls_does_not_hide_duplicate_pending_title() -> None:
    events: list[RawEvent] = [
        {
            "courseId": "1",
            "title": "같은 제목 : Progress stop",
            "date": "내일",
            "desc": "",
            "url": f"https://ecampus.sejong.ac.kr/mod/vod/view.php?id={event_id}",
        }
        for event_id in (1, 2)
    ]
    progress: list[VodProgressRow] = [
        {"title": "같은 제목", "completed": True},
        {"title": "같은 제목", "completed": False},
    ]

    assert completed_video_urls(events, progress) == set()


def test_activity_is_completed_requires_a_finished_quiz_attempt() -> None:
    in_progress = """
    <table class="quizattemptsummary"><tbody><tr>
      <td class="state">Not submitted</td>
      <td><a href="/mod/quiz/attempt.php?attempt=1">계속 응시</a></td>
    </tr></tbody></table>
    """
    finished = """
    <table class="quizattemptsummary"><tbody><tr>
      <td class="state">종료됨</td>
      <td><a href="/mod/quiz/review.php?attempt=1">검토</a></td>
    </tr></tbody></table>
    """

    assert not activity_is_completed("quiz", in_progress)
    assert activity_is_completed("quiz", finished)


def test_normalize_event_date_accepts_both_ampm_orders() -> None:
    before = normalize_event_date("2026년 9월 7일, 오후 11:59")
    after = normalize_event_date("2026년 09월 07일, 11:59 오후")

    assert before == after == "2026-09-07T23:59"


def test_normalize_event_date_resolves_today_and_tomorrow() -> None:
    reference = datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul"))

    assert normalize_event_date("오늘, 오후 11:59", reference) == (
        "2026-09-08T23:59"
    )
    assert normalize_event_date("내일, 오전 12:30", reference) == (
        "2026-09-09T00:30"
    )
