import discord
from datetime import datetime


def _dday(date_str: str) -> str:
    if "오늘" in date_str:
        return "D-0"
    if "내일" in date_str:
        return "D-1"
    return ""


def _time_only(date_str: str) -> str:
    date_str = date_str.strip()
    for prefix in ("오늘, ", "내일, "):
        if date_str.startswith(prefix):
            date_str = date_str[len(prefix):]
    parts = date_str.split()
    if len(parts) == 2 and parts[1] in ("오전", "오후"):
        return f"{parts[1]} {parts[0]}"
    return date_str


def build_embeds(data: dict) -> list[discord.Embed]:
    assignments = data.get("assignments", [])
    quizzes = data.get("quizzes", [])
    videos = data.get("videos", [])

    now = datetime.now()
    timestamp = (
        now.strftime("%Y년 %m월 %d일 %p %I:%M")
        .replace("AM", "오전")
        .replace("PM", "오후")
    )

    embeds = []
    urgent = [e for e in assignments + quizzes if "오늘" in e["date"]]
    upcoming = [e for e in assignments + quizzes if "오늘" not in e["date"]]
    color = 0xE74C3C if urgent else 0x3498DB

    main_embed = discord.Embed(
        title="📋 세종대 과제 현황",
        description=f"기준: {timestamp}",
        color=color,
    )

    if not assignments and not quizzes:
        main_embed.add_field(name="✅ 제출할 과제 없음", value="현재 마감 예정 과제가 없어요.", inline=False)
    else:
        if urgent:
            lines = []
            for e in urgent:
                t = _time_only(e["date"])
                link = f"[바로가기]({e['url']})" if e["url"] else ""
                lines.append(f"**{e['course']}** — {e['title']}\n마감 {t}  {link}")
            main_embed.add_field(name="🔴 오늘 마감", value="\n\n".join(lines), inline=False)
        if upcoming:
            lines = []
            for e in upcoming:
                dday = _dday(e["date"])
                t = _time_only(e["date"])
                label = f"`{dday}`" if dday else ""
                link = f"[바로가기]({e['url']})" if e["url"] else ""
                lines.append(f"{label} **{e['course']}** — {e['title']}\n마감 {t}  {link}")
            main_embed.add_field(name="🟡 예정", value="\n\n".join(lines), inline=False)

    main_embed.set_footer(text="세린이 • 매일 08:00 / 13:00 / 21:00 자동 알림")
    embeds.append(main_embed)

    if videos:
        vid_embed = discord.Embed(title="🎬 동영상 시청 기한", color=0x95A5A6)
        today_vids = [v for v in videos if "오늘" in v["date"]]
        other_vids = [v for v in videos if "오늘" not in v["date"]]
        if today_vids:
            lines = [f"• [{v['course']}] {v['title']}" for v in today_vids]
            vid_embed.add_field(name="오늘 마감", value="\n".join(lines), inline=False)
        if other_vids:
            lines = [f"• [{v['course']}] {v['title']}  ({_time_only(v['date'])})" for v in other_vids]
            vid_embed.add_field(name="예정", value="\n".join(lines), inline=False)
        embeds.append(vid_embed)

    return embeds
