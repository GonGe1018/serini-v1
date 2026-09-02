from datetime import datetime
from typing import Final, TypedDict

import discord
from schedule import REPORT_SCHEDULE_TEXT, TIMEZONE

_FIELD_VALUE_LIMIT: Final = 1024
_MAX_DETAIL_FIELDS: Final = 5


class EventItem(TypedDict):
    course: str
    title: str
    date: str
    desc: str
    url: str


class EventData(TypedDict):
    assignments: list[EventItem]
    quizzes: list[EventItem]
    videos: list[EventItem]
    completed_assignments: list[EventItem]
    completed_quizzes: list[EventItem]
    completed_videos: list[EventItem]


def _time_only(date_str: str) -> str:
    date_str = date_str.strip()
    for prefix in ("오늘, ", "내일, "):
        date_str = date_str.removeprefix(prefix)
    parts = date_str.split()
    if len(parts) == 2 and parts[1] in ("오전", "오후"):
        return f"{parts[1]} {parts[0]}"
    return date_str


def _format_deadline(date_str: str) -> str:
    date_str = date_str.strip()
    if "오늘" in date_str:
        t = _time_only(date_str)
        return f"오늘 {t}"
    if "내일" in date_str:
        t = _time_only(date_str)
        return f"내일 {t}"
    return date_str


def _format_item(item: EventItem) -> str:
    marker = "🔴" if "오늘" in item["date"] else "•"
    link = f" · [열기]({item['url']})" if item["url"] else ""
    return (
        f"{marker} **{item['title']}**\n"
        f"{item['course']} · {_format_deadline(item['date'])}{link}"
    )


def _split_items(items: list[EventItem]) -> list[str]:
    chunks: list[str] = []
    current_items: list[str] = []
    current_length = 0

    for item in items:
        formatted = _format_item(item)[:_FIELD_VALUE_LIMIT]
        added_length = len(formatted) + (2 if current_items else 0)
        if current_items and current_length + added_length > _FIELD_VALUE_LIMIT:
            chunks.append("\n\n".join(current_items))
            current_items = [formatted]
            current_length = len(formatted)
        else:
            current_items.append(formatted)
            current_length += added_length

    if current_items:
        chunks.append("\n\n".join(current_items))
    return chunks


def build_embeds(data: EventData) -> list[discord.Embed]:
    assignments = data["assignments"]
    quizzes = data["quizzes"]
    videos = data["videos"]
    completed_assignments = data["completed_assignments"]
    completed_quizzes = data["completed_quizzes"]
    completed_videos = data["completed_videos"]

    now = datetime.now(TIMEZONE)
    timestamp = (
        now.strftime("%Y년 %m월 %d일 %p %I:%M")
        .replace("AM", "오전")
        .replace("PM", "오후")
    )

    categories = (
        ("📚", "과제", 0xED4245, assignments),
        ("🧩", "퀴즈", 0xFEE75C, quizzes),
        ("🎬", "동영상", 0x5865F2, videos),
    )
    embeds: list[discord.Embed] = []

    for icon, label, color, events in categories:
        if not events:
            continue

        today_count = sum("오늘" in event["date"] for event in events)
        later_count = len(events) - today_count
        deadline_parts: list[str] = []
        if today_count:
            deadline_parts.append(f"오늘 마감 {today_count}개")
        if later_count:
            deadline_parts.append(f"이후 마감 {later_count}개")

        chunks = _split_items(events)
        for start in range(0, len(chunks), _MAX_DETAIL_FIELDS):
            page_number = start // _MAX_DETAIL_FIELDS + 1
            title_suffix = "" if page_number == 1 else f" · {page_number}"
            pending_embed = discord.Embed(
                title=f"{icon} 미완료 {label} · {len(events)}개{title_suffix}",
                description=f"{' · '.join(deadline_parts)}\n{timestamp} 기준",
                color=color,
            )
            for index, chunk in enumerate(chunks[start : start + _MAX_DETAIL_FIELDS]):
                field_name = "일정" if start + index == 0 else "일정 · 계속"
                _ = pending_embed.add_field(name=field_name, value=chunk, inline=False)
            embeds.append(pending_embed)

    completed_categories = (
        ("과제", completed_assignments),
        ("퀴즈", completed_quizzes),
        ("동영상", completed_videos),
    )
    completed_total = sum(len(events) for _, events in completed_categories)
    completed_fields: list[tuple[str, str]] = []
    for label, events in completed_categories:
        chunks = _split_items(events)
        for index, chunk in enumerate(chunks):
            field_name = f"{label} · {len(events)}개" if index == 0 else f"{label} · 계속"
            completed_fields.append((field_name, chunk))

    for start in range(0, len(completed_fields), _MAX_DETAIL_FIELDS):
        page_number = start // _MAX_DETAIL_FIELDS + 1
        title_suffix = "" if page_number == 1 else f" · {page_number}"
        completed_embed = discord.Embed(
            title=f"✅ 완료 · {completed_total}개{title_suffix}",
            description=f"완료한 일정입니다.\n{timestamp} 기준",
            color=0x57F287,
        )
        for field_name, value in completed_fields[start : start + _MAX_DETAIL_FIELDS]:
            _ = completed_embed.add_field(name=field_name, value=value, inline=False)
        embeds.append(completed_embed)

    if not embeds:
        empty_embed = discord.Embed(
            title="✅ 현재 일정 없음",
            description="미완료 또는 완료로 분류된 예정 일정이 없습니다.",
            color=0x57F287,
        )
        for label in ("과제", "퀴즈", "동영상"):
            _ = empty_embed.add_field(name=label, value="일정 없음", inline=True)
        embeds.append(empty_embed)

    _ = embeds[-1].set_footer(
        text=f"세린이 • 매일 {REPORT_SCHEDULE_TEXT} 자동 알림"
    )
    return embeds
