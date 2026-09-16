from datetime import datetime
from typing import ClassVar, cast
from zoneinfo import ZoneInfo

import anyio
import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Request, Route

import scraper
from activity_status import VodProgressRow
from course_activities import CourseActivityLink
from course_vods import CourseVodModule, RawEvent
from ecampus_errors import EcampusLoginError, EcampusScrapeError
from embeds import EventData
from event_enrichment import (
    collect_completed_video_urls,
    enrich_active_course_events,
)
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


class _FakeResponse:
    ok: bool = True
    status: int = 200
    headers: ClassVar[dict[str, str]] = {}

    def __init__(self, url: str, html: str | None = None) -> None:
        self.url: str = url
        self.disposed = False
        self.html = html or """
        시작일시 : 2026-09-01 00:00
        종료일시 : 2026-09-14 23:59
        <table class="quizattemptsummary"><tbody><tr>
          <td class="state">종료됨</td>
        </tr></tbody></table>
        """

    async def text(self) -> str:
        return self.html

    async def dispose(self) -> None:
        self.disposed = True


class _FakeRequest:
    def __init__(
        self,
        html_by_url: dict[str, str] | None = None,
        *,
        stall: bool = False,
    ) -> None:
        self.urls: list[str] = []
        self.responses: list[_FakeResponse] = []
        self.active = 0
        self.max_active = 0
        self.html_by_url = html_by_url or {}
        self.stall = stall

    async def get(
        self,
        url: str,
        *,
        timeout: float,
        max_redirects: int,
    ) -> _FakeResponse:
        assert timeout == 5_000
        assert max_redirects == 0
        self.urls.append(url)
        if self.stall:
            await anyio.sleep_forever()
        if "bad" in url:
            raise EcampusScrapeError
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await anyio.lowlevel.checkpoint()
            response = _FakeResponse(url, self.html_by_url.get(url))
            self.responses.append(response)
            return response
        finally:
            self.active -= 1


class _FakeEnrichmentPage:
    def __init__(
        self,
        activity_links: list[CourseActivityLink] | None = None,
        html_by_url: dict[str, str] | None = None,
        vod_modules: list[CourseVodModule] | None = None,
        stall_requests: bool = False,
    ) -> None:
        self.activity_links: list[CourseActivityLink] = (
            [
                {
                    "title": "정상 퀴즈",
                    "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good",
                }
            ]
            if activity_links is None
            else activity_links
        )
        self.request: _FakeRequest = _FakeRequest(
            html_by_url,
            stall=stall_requests,
        )
        self.vod_modules: list[CourseVodModule] | None = vod_modules

    async def evaluate(
        self,
        expression: str,
        argument: str | None = None,
    ) -> list[CourseVodModule] | list[CourseActivityLink] | list[VodProgressRow]:
        if "/mod/quiz" in expression:
            return self.activity_links
        if argument is not None:
            if self.vod_modules is not None:
                return self.vod_modules
            return [
                {
                    "courseId": argument,
                    "title": "추가 강의",
                    "start": "2026-09-01 00:00:00",
                    "end": "2026-09-14 23:59:59",
                    "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=extra",
                    "completed": True,
                }
            ]
        return [{"title": "정상 강의", "completed": True}]

    async def content(self) -> str:
        return """
        시작일시 : 2026-09-01 00:00
        종료일시 : 2026-09-14 23:59
        <table class="quizattemptsummary"><tbody><tr>
          <td class="state">종료됨</td>
        </tr></tbody></table>
        """


@pytest.mark.asyncio
async def test_course_page_enrichment_completes_unlisted_events() -> None:
    page = cast(Page, cast(object, _FakeEnrichmentPage()))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "추가 강의 : Progress stop",
            "date": "2026년 9월 14일, 오후 11:59",
            "desc": "",
            "url": "",
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    completed_urls = await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert completed_urls == {
        "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=extra",
        "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good",
    }
    assert [event["url"] for event in raw] == [
        "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=extra",
        "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good",
    ]


@pytest.mark.asyncio
async def test_course_page_restores_missing_quiz_url() -> None:
    page = cast(Page, cast(object, _FakeEnrichmentPage()))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "정상 퀴즈 closes",
            "date": "오늘",
            "desc": "",
            "url": "",
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert raw[0]["url"] == (
        "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good"
    )
    assert sum(event["url"].endswith("id=good") for event in raw) == 1


@pytest.mark.asyncio
async def test_course_page_restores_assignment_url_from_description() -> None:
    page = cast(
        Page,
        cast(
            object,
            _FakeEnrichmentPage(
                [
                    {
                        "title": "연습문제 제출",
                        "url": (
                            "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=work"
                        ),
                    }
                ]
            ),
        ),
    )
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "마감 기한",
            "date": "오늘",
            "desc": "연습문제 제출\n설명",
            "url": "",
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assignment_events = [event for event in raw if event["title"] == "마감 기한"]
    assert assignment_events == [
        {
            "courseId": "good-course",
            "title": "마감 기한",
            "date": "오늘",
            "desc": "연습문제 제출\n설명",
            "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=work",
        }
    ]


@pytest.mark.asyncio
async def test_course_page_replaces_calendar_description_with_assignment_title() -> None:
    # Given
    url = "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=390325"
    page = cast(
        Page,
        cast(
            object,
            _FakeEnrichmentPage(
                [{"title": "3주차 과제 - 갓생 1차 글쓰기", "url": url}],
                {
                    url: """
                    <div class="submissionstatustable"><table>
                      <tr><td>제출 여부</td><td class="submissionstatussubmitted">제출 완료</td></tr>
                      <tr><td>종료 일시</td><td>2026-09-21 23:59</td></tr>
                    </table></div>
                    """
                },
                vod_modules=[],
            ),
        ),
    )
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "마감 기한",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "강의 시간에 작성한 문단쓰기를 업로드하길 바랍니다.",
            "url": "",
        }
    ]

    async def navigate(
        current_page: Page,
        destination: str,
        expected_selector: str,
    ) -> None:
        del current_page, destination, expected_selector

    # When
    completed_urls = await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 16, 18, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    # Then
    assert raw == [
        {
            "courseId": "good-course",
            "title": "마감 기한",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "3주차 과제 - 갓생 1차 글쓰기",
            "url": url,
        }
    ]
    assert completed_urls == {url}


@pytest.mark.asyncio
async def test_course_page_fetches_all_activities_with_bounded_concurrency() -> None:
    links: list[CourseActivityLink] = [
        {
            "title": f"퀴즈 {index}",
            "url": f"https://ecampus.sejong.ac.kr/mod/quiz/view.php?id={index}",
        }
        for index in range(20)
    ]
    fake_page = _FakeEnrichmentPage(links)
    page = cast(Page, cast(object, fake_page))

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        [],
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert len(fake_page.request.urls) == 20
    assert fake_page.request.max_active <= 4
    assert all(response.disposed for response in fake_page.request.responses)


@pytest.mark.asyncio
async def test_course_activity_batch_honors_outer_deadline() -> None:
    page = cast(
        Page,
        cast(object, _FakeEnrichmentPage(stall_requests=True)),
    )

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.01):
            await enrich_active_course_events(
                page,
                ["good-course"],
                [],
                datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
                navigate,
            )


@pytest.mark.asyncio
async def test_course_page_does_not_reuse_one_url_for_duplicate_rows() -> None:
    page = cast(Page, cast(object, _FakeEnrichmentPage()))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "정상 퀴즈 closes",
            "date": "2026년 9월 14일, 오후 11:59",
            "desc": "",
            "url": "",
        }
        for _ in range(2)
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    quiz_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good"
    assert sum(event["url"] == quiz_url for event in raw) == 1
    data = _partition_events(raw, {"good-course": "강좌"}, set())
    assert len(data["quizzes"]) == 1


@pytest.mark.asyncio
async def test_course_page_fetches_existing_activity_url_once() -> None:
    fake_page = _FakeEnrichmentPage()
    page = cast(Page, cast(object, fake_page))
    quiz_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good"
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "정상 퀴즈 closes",
            "date": "2026년 9월 14일, 오후 11:59",
            "desc": "",
            "url": quiz_url,
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert fake_page.request.urls.count(quiz_url) == 1


@pytest.mark.asyncio
async def test_course_page_matches_repeated_titles_by_normalized_date() -> None:
    early_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=early"
    late_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=late"
    fake_page = _FakeEnrichmentPage(
        [
            {"title": "주간 퀴즈", "url": early_url},
            {"title": "주간 퀴즈", "url": late_url},
        ],
        {
            early_url: "시작일시 : 2026-09-01 00:00 종료일시 : 2026-09-14 23:59",
            late_url: "시작일시 : 2026-09-01 00:00 종료일시 : 2026-09-21 23:59",
        },
    )
    page = cast(Page, cast(object, fake_page))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "주간 퀴즈 closes",
            "date": date,
            "desc": "",
            "url": "",
        }
        for date in (
            "2026년 9월 21일, 11:59 오후",
            "2026년 09월 14일, 오후 11:59",
        )
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert [event["url"] for event in raw[:2]] == [late_url, early_url]


@pytest.mark.asyncio
async def test_course_page_matches_repeated_vods_by_normalized_date() -> None:
    early_url = "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=early"
    late_url = "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=late"
    modules: list[CourseVodModule] = [
        {
            "courseId": "good-course",
            "title": "반복 강의",
            "start": "2026-09-01 00:00:00",
            "end": end,
            "url": url,
            "completed": False,
        }
        for end, url in (
            ("2026-09-14 23:59:00", early_url),
            ("2026-09-21 23:59:00", late_url),
        )
    ]
    fake_page = _FakeEnrichmentPage(activity_links=[], vod_modules=modules)
    page = cast(Page, cast(object, fake_page))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "반복 강의 : Progress stop",
            "date": date,
            "desc": "",
            "url": "",
        }
        for date in (
            "2026년 9월 21일, 11:59 오후",
            "2026년 09월 14일, 오후 11:59",
        )
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert [event["url"] for event in raw] == [late_url, early_url]


@pytest.mark.asyncio
async def test_course_page_removes_inactive_vod_calendar_row() -> None:
    vod_url = "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=future"
    modules: list[CourseVodModule] = [
        {
            "courseId": "good-course",
            "title": "미래 강의",
            "start": "2026-09-15 00:00:00",
            "end": "2026-09-21 23:59:00",
            "url": vod_url,
            "completed": False,
        }
    ]
    page = cast(
        Page,
        cast(
            object,
            _FakeEnrichmentPage(activity_links=[], vod_modules=modules),
        ),
    )
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "미래 강의 : Progress stop",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "",
            "url": vod_url,
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert raw == []


@pytest.mark.asyncio
async def test_course_page_removes_calendar_activity_outside_active_window() -> None:
    quiz_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good"
    fake_page = _FakeEnrichmentPage(
        html_by_url={
            quiz_url: "시작일시 : 2026-09-15 00:00 종료일시 : 2026-09-21 23:59"
        }
    )
    page = cast(Page, cast(object, fake_page))
    raw: list[RawEvent] = [
        {
            "courseId": "good-course",
            "title": "정상 퀴즈 closes",
            "date": "2026년 9월 21일, 오후 11:59",
            "desc": "",
            "url": quiz_url,
        }
    ]

    async def navigate(
        current_page: Page,
        url: str,
        expected_selector: str,
    ) -> None:
        del current_page, url, expected_selector

    await enrich_active_course_events(
        page,
        ["good-course"],
        raw,
        datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
        navigate,
    )

    assert all(event["url"] != quiz_url for event in raw)


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

    completed_urls = await enrich_active_course_events(
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
    assert any(event["url"].endswith("id=extra") for event in raw)
    assert completed_videos == {
        "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=good"
    }
    assert "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=good" in completed_urls


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
        await enrich_active_course_events(
            page,
            ["course"],
            [],
            datetime(2026, 9, 2, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
            login_redirect,
        )


def test_partition_events_collapses_duplicate_calendar_rows() -> None:
    raw: list[RawEvent] = [
        {
            "courseId": "course",
            "title": "중복 퀴즈 closes",
            "date": "오늘",
            "desc": "",
            "url": url,
        }
        for url in (
            "",
            "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=one",
        )
    ]

    data = _partition_events(raw, {"course": "강좌"}, set())

    assert len(data["quizzes"]) == 1
    assert data["quizzes"][0]["url"].endswith("id=one")


def test_partition_events_merges_relative_date_and_prefers_completed_url() -> None:
    quiz_url = "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=one"
    raw: list[RawEvent] = [
        {
            "courseId": "course",
            "title": "오늘 퀴즈 closes",
            "date": date,
            "desc": "",
            "url": url,
        }
        for date, url in (
            ("오늘, 오후 11:59", ""),
            ("2026년 9월 8일, 오후 11:59", quiz_url),
        )
    ]

    data = _partition_events(
        raw,
        {"course": "강좌"},
        {quiz_url},
        datetime(2026, 9, 8, 14, 0, tzinfo=ZoneInfo("Asia/Seoul")),
    )

    assert data["quizzes"] == []
    assert [item["url"] for item in data["completed_quizzes"]] == [quiz_url]


def test_partition_events_preserves_interleaved_distinct_url_order() -> None:
    raw: list[RawEvent] = [
        {
            "courseId": "course",
            "title": title,
            "date": "오늘",
            "desc": "",
            "url": f"https://ecampus.sejong.ac.kr/mod/quiz/view.php?id={event_id}",
        }
        for title, event_id in (("A 퀴즈", "a1"), ("B 퀴즈", "b"), ("A 퀴즈", "a2"))
    ]

    data = _partition_events(raw, {"course": "강좌"}, set())

    assert [item["title"] for item in data["quizzes"]] == [
        "A 퀴즈",
        "B 퀴즈",
        "A 퀴즈",
    ]


@pytest.mark.asyncio
async def test_scrape_deadline_translates_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeBrowser:
        def __init__(self, *, fail_close: bool = False) -> None:
            self.closed = False
            self.fail_close = fail_close

        async def new_page(self) -> Page:
            return cast(Page, cast(object, object()))

        async def close(self) -> None:
            await anyio.lowlevel.checkpoint()
            if self.fail_close:
                raise PlaywrightError("close failed")
            self.closed = True

    class FakeChromium:
        def __init__(self, browser: FakeBrowser) -> None:
            self.browser = browser

        async def launch(self, *, headless: bool) -> FakeBrowser:
            assert headless
            return self.browser

    class FakePlaywright:
        def __init__(self, browser: FakeBrowser) -> None:
            self.chromium = FakeChromium(browser)
            self.stopped = False

        async def stop(self) -> None:
            await anyio.lowlevel.checkpoint()
            self.stopped = True

    class FakeManager:
        def __init__(self, playwright: FakePlaywright) -> None:
            self.playwright = playwright

        async def start(self) -> FakePlaywright:
            return self.playwright

    async def stalled_collect(
        page: Page,
        ecampus_id: str,
        ecampus_pw: str,
    ) -> EventData:
        del page, ecampus_id, ecampus_pw
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    browser = FakeBrowser()
    manager = FakeManager(FakePlaywright(browser))
    monkeypatch.setattr(scraper, "_SCRAPE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(scraper, "async_playwright", lambda: manager)
    monkeypatch.setattr(scraper, "_collect_upcoming_events", stalled_collect)

    with pytest.raises(EcampusScrapeError):
        await scraper.get_upcoming_events("user", "password")
    assert browser.closed
    assert manager.playwright.stopped

    browser = FakeBrowser(fail_close=True)
    manager = FakeManager(FakePlaywright(browser))
    monkeypatch.setattr(scraper, "_SCRAPE_TIMEOUT_SECONDS", 0.01)
    with pytest.raises(EcampusScrapeError):
        await scraper.get_upcoming_events("close-failure", "password")
    assert not browser.closed
    assert manager.playwright.stopped

    browser = FakeBrowser()
    manager = FakeManager(FakePlaywright(browser))
    monkeypatch.setattr(scraper, "_SCRAPE_TIMEOUT_SECONDS", 90)
    with anyio.move_on_after(0.01) as scope:
        await scraper.get_upcoming_events("externally-cancelled", "password")
    assert scope.cancel_called
    assert browser.closed
    assert manager.playwright.stopped


@pytest.mark.asyncio
async def test_request_route_blocks_cross_origin_subresources() -> None:
    class FakeRoute:
        def __init__(self) -> None:
            self.action = ""

        async def abort(self) -> None:
            self.action = "abort"

        async def continue_(self) -> None:
            self.action = "continue"

    class FakeRequest:
        url = "http://169.254.169.254/latest/meta-data/"

    route = FakeRoute()
    await scraper._route_ecampus_navigation(
        cast(Route, cast(object, route)),
        cast(Request, cast(object, FakeRequest())),
    )

    assert route.action == "abort"


@pytest.mark.asyncio
async def test_scrape_admission_rejects_duplicate_and_excess_browsers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = 0
    peak = 0
    both_started = anyio.Event()
    release = anyio.Event()

    async def controlled_scrape(ecampus_id: str, ecampus_pw: str) -> EventData:
        nonlocal peak, started
        del ecampus_id, ecampus_pw
        started += 1
        peak = max(peak, started)
        if started == 2:
            both_started.set()
        try:
            await release.wait()
        finally:
            started -= 1
        return {
            "assignments": [],
            "quizzes": [],
            "videos": [],
            "completed_assignments": [],
            "completed_quizzes": [],
            "completed_videos": [],
        }

    monkeypatch.setattr(scraper, "_scrape_upcoming_events", controlled_scrape)
    results: list[EventData] = []

    async def run_scrape(ecampus_id: str) -> None:
        results.append(await scraper.get_upcoming_events(ecampus_id, "password"))

    async with anyio.create_task_group() as task_group:
        _ = task_group.start_soon(run_scrape, "user-one")
        _ = task_group.start_soon(run_scrape, "user-two")
        await both_started.wait()
        with pytest.raises(EcampusScrapeError):
            await scraper.get_upcoming_events("user-one", "password")
        with pytest.raises(EcampusScrapeError):
            await scraper.get_upcoming_events("user-three", "password")
        release.set()

    assert peak == 2
    assert len(results) == 2


@pytest.mark.asyncio
async def test_scrape_admission_releases_slot_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stalled_scrape(ecampus_id: str, ecampus_pw: str) -> EventData:
        del ecampus_id, ecampus_pw
        await anyio.sleep_forever()
        raise AssertionError("unreachable")

    async def successful_scrape(ecampus_id: str, ecampus_pw: str) -> EventData:
        del ecampus_id, ecampus_pw
        return {
            "assignments": [],
            "quizzes": [],
            "videos": [],
            "completed_assignments": [],
            "completed_quizzes": [],
            "completed_videos": [],
        }

    monkeypatch.setattr(scraper, "_scrape_upcoming_events", stalled_scrape)
    with anyio.move_on_after(0.01) as scope:
        await scraper.get_upcoming_events("cancelled-user", "password")
    assert scope.cancel_called

    monkeypatch.setattr(scraper, "_scrape_upcoming_events", successful_scrape)
    result = await scraper.get_upcoming_events("cancelled-user", "password")

    assert result["quizzes"] == []
