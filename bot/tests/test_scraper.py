from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

import pytest
import scraper
from course_vods import RawEvent
from ecampus_errors import EcampusLoginError, EcampusScrapeError
from event_enrichment import (
    append_active_course_vods,
    collect_completed_activity_urls,
    collect_completed_video_urls,
)
from playwright.async_api import Page
from scraper import _partition_events


def test_partition_events_excludes_video_starts_and_separates_completed_videos() -> None:
    raw: list[RawEvent] = [
        {
            "courseId": "33609",
            "title": "강의 1주차 : Progress stop",
            "date": "2026년 9월 07일, 11:59 오후",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=1",
        },
        {
            "courseId": "33609",
            "title": "강의 2주차 : Progress stop",
            "date": "2026년 9월 07일, 11:59 오후",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=2",
        },
        {
            "courseId": "33609",
            "title": "강의 3주차 : Progress start",
            "date": "2026년 9월 08일, 12:00 오전",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=3",
        },
    ]

    data = _partition_events(
        raw,
        {"33609": "테스트 강좌"},
        {"https://ecampus.sejong.ac.kr/mod/vod/view.php?id=1"},
    )

    assert [item["title"] for item in data["videos"]] == ["강의 2주차"]
    assert [item["title"] for item in data["completed_videos"]] == ["강의 1주차"]


class _FakeEnrichmentPage:
    async def evaluate(
        self,
        expression: str,
        argument: str | None = None,
    ) -> object:
        if argument is not None:
            return [
                {
                    "courseId": argument,
                    "title": "추가 강의",
                    "start": "2026-09-01 00:00:00",
                    "end": "2026-09-14 23:59:59",
                    "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=extra",
                }
            ]
        return [{"title": "정상 강의", "completed": True}]

    async def content(self) -> str:
        return """
        <table class="quizattemptsummary"><tbody><tr>
          <td class="state">종료됨</td>
        </tr></tbody></table>
        """


@pytest.mark.asyncio
async def test_optional_enrichment_failures_keep_healthy_course_results() -> None:
    page = cast(Page, cast(object, _FakeEnrichmentPage()))
    raw: list[RawEvent] = [
        {
            "courseId": course_id,
            "title": title,
            "date": "2026년 9월 14일, 오후 11:59",
            "desc": "",
            "url": url,
        }
        for course_id, title, url in (
            (
                "bad-course",
                "실패 강의 : Progress stop",
                "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=bad",
            ),
            (
                "good-course",
                "정상 강의 : Progress stop",
                "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=good",
            ),
            (
                "bad-course",
                "실패 퀴즈",
                "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=bad",
            ),
            (
                "good-course",
                "정상 퀴즈",
                "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good",
            ),
        )
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, expected_selector
        if "bad" in url:
            raise EcampusScrapeError

    await append_active_course_vods(
        page,
        ["bad-course", "good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )
    completed_videos = await collect_completed_video_urls(
        page,
        raw,
        scraper._classify,
        navigate,
    )
    completed_activities = await collect_completed_activity_urls(
        page,
        raw,
        scraper._classify,
        navigate,
    )

    assert any(event["url"].endswith("id=extra") for event in raw)
    assert completed_videos == {
        "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=good"
    }
    assert completed_activities == {
        "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good"
    }


@pytest.mark.asyncio
async def test_optional_enrichment_does_not_swallow_login_redirects() -> None:
    page = cast(Page, cast(object, _FakeEnrichmentPage()))

    async def login_redirect(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector
        raise EcampusLoginError

    with pytest.raises(EcampusLoginError):
        await append_active_course_vods(
            page,
            ["course"],
            [],
            datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
            login_redirect,
        )
