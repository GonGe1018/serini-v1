from embeds import EventData, EventItem, build_embeds


def test_build_embeds_marks_every_category_complete_when_nothing_is_due() -> None:
    # Given
    data: EventData = {
        "assignments": [],
        "quizzes": [],
        "videos": [],
        "completed_assignments": [],
        "completed_quizzes": [],
        "completed_videos": [],
    }

    # When
    embeds = build_embeds(data)

    # Then
    assert len(embeds) == 1
    assert embeds[0].title == "✅ 현재 일정 없음"
    assert [field.name for field in embeds[0].fields[:3]] == [
        "과제",
        "퀴즈",
        "동영상",
    ]


def test_build_embeds_separates_pending_items_from_completed_items() -> None:
    # Given
    data: EventData = {
        "assignments": [
            {
                "course": "자료구조",
                "title": "연결 리스트 과제",
                "date": "오늘, 11:59 오후",
                "desc": "",
                "url": "https://ecampus.sejong.ac.kr/mod/assign/view.php?id=1",
            },
        ],
        "quizzes": [],
        "videos": [
            {
                "course": "운영체제",
                "title": "프로세스와 스레드",
                "date": "내일, 11:59 오후",
                "desc": "",
                "url": "",
            },
        ],
        "completed_assignments": [],
        "completed_quizzes": [
            {
                "course": "자료구조",
                "title": "1주차 퀴즈",
                "date": "내일, 11:59 오후",
                "desc": "",
                "url": "https://ecampus.sejong.ac.kr/mod/quiz/view.php?id=2",
            },
        ],
        "completed_videos": [],
    }

    # When
    embeds = build_embeds(data)

    # Then
    assert len(embeds) == 3
    assert [embed.title for embed in embeds] == [
        "📚 미완료 과제 · 1개",
        "🎬 미완료 동영상 · 1개",
        "✅ 완료 · 1개",
    ]
    assignment_details = embeds[0].fields[0].value
    video_details = embeds[1].fields[0].value
    assert assignment_details is not None
    assert video_details is not None
    assert "자료구조" in assignment_details
    assert "운영체제" in video_details
    assert [field.name for field in embeds[2].fields] == ["퀴즈 · 1개"]
    completed_details = embeds[2].fields[0].value
    assert completed_details is not None
    assert "1주차 퀴즈" in completed_details


def test_build_embeds_keeps_long_category_fields_within_discord_limit() -> None:
    # Given
    videos: list[EventItem] = [
        {
            "course": "운영체제",
            "title": f"프로세스와 스레드 심화 학습 {index}",
            "date": "내일, 11:59 오후",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=12345",
        }
        for index in range(20)
    ]
    data: EventData = {
        "assignments": [],
        "quizzes": [],
        "videos": videos,
        "completed_assignments": [],
        "completed_quizzes": [],
        "completed_videos": [],
    }

    # When
    embeds = build_embeds(data)
    video_embed = next(embed for embed in embeds if embed.title and "동영상" in embed.title)

    # Then
    assert all(
        field.value is not None and len(field.value) <= 1024
        for field in video_embed.fields
    )
    video_fields = [
        field
        for field in video_embed.fields
        if field.name is not None and field.name.startswith("일정")
    ]
    assert len(video_fields) > 1


def test_build_embeds_paginates_before_discord_embed_limits() -> None:
    # Given
    videos: list[EventItem] = [
        {
            "course": "운영체제",
            "title": f"긴 동영상 학습 일정 {index}",
            "date": "내일, 11:59 오후",
            "desc": "",
            "url": "https://ecampus.sejong.ac.kr/mod/vod/view.php?id=12345",
        }
        for index in range(100)
    ]
    data: EventData = {
        "assignments": [],
        "quizzes": [],
        "videos": videos,
        "completed_assignments": [],
        "completed_quizzes": [],
        "completed_videos": [],
    }

    # When
    embeds = build_embeds(data)

    # Then
    for embed in embeds:
        text_length = len(embed.title or "") + len(embed.description or "")
        text_length += len(embed.footer.text or "")
        text_length += sum(
            len(field.name or "") + len(field.value or "") for field in embed.fields
        )
        assert len(embed.fields) <= 5
        assert text_length <= 6000
