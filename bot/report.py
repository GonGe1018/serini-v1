import asyncio
import logging
import discord
from shared.database import get_session, User
from shared.crypto import decrypt
from scraper import get_upcoming_events
from embeds import build_embeds

logger = logging.getLogger(__name__)

_LOGIN_FAIL_MSG = (
    "⚠️ 집현캠퍼스 로그인에 실패했습니다.\n"
    "비밀번호가 변경되었다면 `!비밀번호`로 업데이트해주세요."
)


def _is_empty_data(data: dict) -> bool:
    return not data.get("assignments") and not data.get("quizzes") and not data.get("videos")


class UpdateReportView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="업데이트", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="update_report")
    async def update_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = "로딩 중..."
        button.emoji = "⏳"
        button.disabled = True
        await interaction.response.edit_message(view=self)

        try:
            db = get_session()
            try:
                user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
                if not user:
                    await interaction.channel.send("가입 정보가 없습니다. `!가입`으로 신청해주세요.")
                    return
                if user.status != "approved":
                    await interaction.channel.send("아직 승인되지 않았습니다. `!상태`로 확인해보세요.")
                    return
                ecampus_pw = decrypt(user.ecampus_pw_enc)
                data = await get_upcoming_events(user.ecampus_id, ecampus_pw)
            finally:
                db.close()

            bot_user_id = interaction.client.user.id
            await clear_dm(interaction.channel, bot_user_id)

            if _is_empty_data(data):
                await interaction.channel.send(_LOGIN_FAIL_MSG, view=UpdateReportView())
                return

            embeds = build_embeds(data)
            view = UpdateReportView()
            for i, embed in enumerate(embeds):
                if i == len(embeds) - 1:
                    await interaction.channel.send(embed=embed, view=view)
                else:
                    await interaction.channel.send(embed=embed)
        except Exception:
            logger.exception("Failed to update report for user %s", interaction.user.id)
            await interaction.channel.send("업데이트 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")


async def clear_dm(channel: discord.DMChannel, bot_user_id: int):
    async for msg in channel.history(limit=300):
        if msg.author.id == bot_user_id:
            await msg.delete()
            await asyncio.sleep(0.3)


async def clear_and_send(channel: discord.DMChannel, discord_id: int, bot_user_id: int):
    try:
        db = get_session()
        try:
            user = db.query(User).filter(User.discord_id == str(discord_id)).first()
            if not user or user.status != "approved":
                return
            ecampus_pw = decrypt(user.ecampus_pw_enc)
            data = await get_upcoming_events(user.ecampus_id, ecampus_pw)
        finally:
            db.close()

        await clear_dm(channel, bot_user_id)

        if _is_empty_data(data):
            await channel.send(_LOGIN_FAIL_MSG, view=UpdateReportView())
            return

        embeds = build_embeds(data)
        view = UpdateReportView()
        for i, embed in enumerate(embeds):
            if i == len(embeds) - 1:
                await channel.send(embed=embed, view=view)
            else:
                await channel.send(embed=embed)
    except Exception:
        logger.exception("Failed to send report for user %s", discord_id)


async def send_report_to_all(client: discord.Client):
    db = get_session()
    try:
        approved_users = db.query(User).filter(User.status == "approved").all()
        user_data = [(u.discord_id, u.ecampus_id, u.ecampus_pw_enc) for u in approved_users]
    finally:
        db.close()

    for discord_id_str, _, _ in user_data:
        try:
            discord_id = int(discord_id_str)
            discord_user = await client.fetch_user(discord_id)
            dm = await discord_user.create_dm()
            await clear_and_send(dm, discord_id, client.user.id)
        except Exception:
            logger.exception("Failed to send report to %s", discord_id_str)
