from datetime import datetime
from zoneinfo import ZoneInfo

from course_activities import (
    ActiveCourseActivity,
    CourseActivityModule,
    active_course_activity,
    is_course_activity_url,
)


def test_active_course_activity_includes_completed_quiz() -> None:
    # Given
    module: CourseActivityModule = {
        "courseId": "33122",
        "title": "2주차 온라인 퀴즈",
        "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=372831",
    }
    html = """
    <main>
      시작일시 : 2026-09-08 00:00
      종료일시 : 2026-09-21 23:59
      <table class="quizattemptsummary"><tbody><tr>
        <td class="state">종료됨</td>
      </tr></tbody></table>
    </main>
    """

    # When
    result = active_course_activity(
        module,
        html,
        datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    # Then
    assert result == ActiveCourseActivity(
        event={
            "courseId": "33122",
            "title": "2주차 온라인 퀴즈 closes",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=372831",
        },
        completed=True,
    )


def test_active_course_activity_excludes_locked_future_quiz() -> None:
    # Given
    module: CourseActivityModule = {
        "courseId": "33122",
        "title": "3주차 온라인 퀴즈",
        "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=372835",
    }
    html = """
    <main>
      2026-09-15 00:00 까지는 퀴즈를 이용할 수 없음
      종료일시 : 2026-09-28 23:59
    </main>
    """

    # When
    result = active_course_activity(
        module,
        html,
        datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    # Then
    assert result is None


def test_active_course_activity_includes_assignment() -> None:
    # Given
    module: CourseActivityModule = {
        "courseId": "31329",
        "title": "연습문제 제출",
        "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=400000",
    }
    html = """
    <main>
      제출 시작 : 2026-09-08 00:00
      마감 일시 : 2026-09-20 18:30
      <div class="submissionstatussubmitted">제출 완료</div>
    </main>
    """

    # When
    result = active_course_activity(
        module,
        html,
        datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    # Then
    assert result == ActiveCourseActivity(
        event={
            "courseId": "31329",
            "title": "마감 기한",
            "date": "2026년 9월 20일, 오후 6:30",
            "desc": "연습문제 제출",
            "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=400000",
        },
        completed=True,
    )


def test_active_course_activity_reads_submission_table_without_colons() -> None:
    # Given
    module: CourseActivityModule = {
        "courseId": "33609",
        "title": "3주차 과제 - 갓생 1차 글쓰기",
        "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=390325",
    }
    html = """
    <div class="submissionstatustable">
      <table>
        <tr><td>제출 여부</td><td class="submissionstatussubmitted">제출 완료</td></tr>
        <tr><td>종료 일시</td><td>2026-09-21 23:59</td></tr>
      </table>
    </div>
    """

    # When
    result = active_course_activity(
        module,
        html,
        datetime(2026, 9, 16, 18, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    # Then
    assert result == ActiveCourseActivity(
        event={
            "courseId": "33609",
            "title": "마감 기한",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "3주차 과제 - 갓생 1차 글쓰기",
            "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=390325",
        },
        completed=True,
    )


def test_course_activity_url_requires_expected_ecampus_path() -> None:
    assert is_course_activity_url(
        "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=1"
    )
    assert not is_course_activity_url(
        "https://attacker.example/mod/quiz/view.php?id=1"
    )
    assert not is_course_activity_url(
        "https://ecampus.sejong.ac.kr/course/view.php?id=1"
    )


def test_active_course_activity_ignores_malformed_deadline() -> None:
    module: CourseActivityModule = {
        "courseId": "33122",
        "title": "잘못된 퀴즈",
        "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=broken",
    }

    result = active_course_activity(
        module,
        "종료일시 : 2026-99-99 23:59",
        datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert result is None
