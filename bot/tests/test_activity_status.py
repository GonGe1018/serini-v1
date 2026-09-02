from activity_status import (
    VodProgressRow,
    activity_is_completed,
    completed_video_urls,
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
