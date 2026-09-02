from dataclasses import dataclass
from unittest.mock import MagicMock

import discord
import pytest
import report


@dataclass(frozen=True, slots=True)
class SentMessage:
    content: str | None
    embed: discord.Embed | None


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    async def send(
        self,
        content: str | None = None,
        *,
        embed: discord.Embed | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        self.sent.append(SentMessage(content=content, embed=embed))


@pytest.mark.asyncio
async def test_clear_and_send_shows_no_events_when_calendar_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    user = MagicMock(status="approved", ecampus_pw_enc="encrypted", ecampus_id="student")
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = user
    channel = FakeChannel()

    async def empty_calendar(ecampus_id: str, ecampus_pw: str) -> dict[str, list[dict[str, str]]]:
        return {
            "assignments": [],
            "quizzes": [],
            "videos": [],
            "completed_assignments": [],
            "completed_quizzes": [],
            "completed_videos": [],
        }

    async def skip_clear(channel: FakeChannel, bot_user_id: int) -> None:
        return None

    monkeypatch.setattr(report, "get_session", lambda: session)
    monkeypatch.setattr(report, "decrypt", lambda token: "password")
    monkeypatch.setattr(report, "get_upcoming_events", empty_calendar)
    monkeypatch.setattr(report, "clear_dm", skip_clear)

    await report.clear_and_send(channel, discord_id=1, bot_user_id=2)

    assert len(channel.sent) == 1
    assert channel.sent[0].content is None
    assert channel.sent[0].embed is not None
    assert [field.name for field in channel.sent[0].embed.fields[:3]] == [
        "과제",
        "퀴즈",
        "동영상",
    ]


@pytest.mark.asyncio
async def test_clear_and_send_shows_login_error_only_for_login_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    user = MagicMock(status="approved", ecampus_pw_enc="encrypted", ecampus_id="student")
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = user
    channel = FakeChannel()

    async def login_failure(ecampus_id: str, ecampus_pw: str) -> dict[str, list[dict[str, str]]]:
        raise report.EcampusLoginError

    async def skip_clear(channel: FakeChannel, bot_user_id: int) -> None:
        return None

    monkeypatch.setattr(report, "get_session", lambda: session)
    monkeypatch.setattr(report, "decrypt", lambda token: "password")
    monkeypatch.setattr(report, "get_upcoming_events", login_failure)
    monkeypatch.setattr(report, "clear_dm", skip_clear)

    await report.clear_and_send(channel, discord_id=1, bot_user_id=2)

    assert len(channel.sent) == 1
    assert channel.sent[0].content is not None
    assert "로그인에 실패" in channel.sent[0].content
    assert "/비밀번호" in channel.sent[0].content
