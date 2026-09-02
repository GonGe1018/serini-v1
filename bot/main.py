import logging

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import bot_settings
from discord import app_commands
from registration import CheckApprovalView, PasswordChangeModal, registration_flow
from report import UpdateReportView, clear_and_send, send_report_to_all
from schedule import REPORT_SCHEDULE_TEXT, REPORT_TIMES, TIMEZONE, next_report_time
from shared.database import User, get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
_ready_fired = False


@tree.command(name="가입", description="세린이 서비스 가입 신청")
async def cmd_register(interaction: discord.Interaction):
    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
    finally:
        db.close()

    if user:
        status_msg = {"pending": "이미 가입 신청이 접수되어 있습니다. 관리자 승인을 기다려주세요.", "approved": "이미 승인된 계정입니다.", "rejected": "이전에 거절되었습니다. 다시 신청하려면 `/탈퇴` 후 `/가입`해주세요."}
        await interaction.response.send_message(status_msg.get(user.status, "이미 가입된 계정입니다."), ephemeral=True)
        return

    await registration_flow(interaction)


@tree.command(name="clear", description="봇이 보낸 메시지 모두 삭제")
async def cmd_clear(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    from report import clear_dm
    await clear_dm(interaction.channel, client.user.id)
    await interaction.followup.send("✅ 봇 메시지를 모두 삭제했습니다.", ephemeral=True)


@tree.command(name="도움말", description="세린이 명령어 안내")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🦒 세린이 도움말",
        color=0x5865F2,
        description=(
            "세종대 과제 알림 봇입니다.\n"
            f"매일 {REPORT_SCHEDULE_TEXT}에 과제 현황을 알려드려요."
        ),
    )
    embed.add_field(
        name="명령어",
        value=(
            "`/가입` — 서비스 가입 신청\n"
            "`/상태` — 승인 상태 및 다음 알림 시간 확인\n"
            "`/비밀번호` — 집현캠퍼스 비밀번호 변경\n"
            "`/업데이트` — 과제 현황 즉시 업데이트\n"
            "`/탈퇴` — 서비스 탈퇴 및 데이터 삭제\n"
            "`/clear` — 봇 메시지 모두 삭제\n"
            "`/도움말` — 이 도움말 보기"
        ),
        inline=False,
    )
    embed.set_footer(text="문제가 있으면 관리자에게 문의해주세요.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="상태", description="승인 상태 및 다음 알림 시간 확인")
async def cmd_status(interaction: discord.Interaction):
    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
    finally:
        db.close()

    if not user:
        await interaction.response.send_message("가입 정보가 없습니다. `/가입`으로 신청해주세요.", ephemeral=True)
        return

    status_map = {"pending": "⏳ 승인 대기 중", "approved": "✅ 승인됨", "rejected": "❌ 거절됨"}
    embed = discord.Embed(title="📋 내 상태", color=0x3498DB)
    embed.add_field(name="상태", value=status_map.get(user.status, user.status), inline=True)
    embed.add_field(name="학번", value=user.ecampus_id, inline=True)
    if user.status == "approved":
        embed.add_field(name="다음 알림", value=f"{next_report_time()} (KST)", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="비밀번호", description="집현캠퍼스 비밀번호 변경")
async def cmd_password(interaction: discord.Interaction):
    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
    finally:
        db.close()

    if not user:
        await interaction.response.send_message("가입 정보가 없습니다. `/가입`으로 먼저 신청해주세요.", ephemeral=True)
        return

    await interaction.response.send_modal(PasswordChangeModal())


@tree.command(name="업데이트", description="과제 현황 즉시 업데이트")
async def cmd_update(interaction: discord.Interaction):
    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
        if not user or user.status != "approved":
            await interaction.response.send_message("승인된 계정이 아닙니다.", ephemeral=True)
            return
    finally:
        db.close()

    await interaction.response.defer()
    await clear_and_send(interaction.channel, interaction.user.id, client.user.id)


@tree.command(name="탈퇴", description="서비스 탈퇴 및 데이터 삭제")
async def cmd_withdraw(interaction: discord.Interaction):
    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
    finally:
        db.close()

    if not user:
        await interaction.response.send_message("가입 정보가 없습니다.", ephemeral=True)
        return

    view = _WithdrawView(interaction.user.id)
    await interaction.response.send_message(
        "⚠️ 정말 탈퇴하시겠습니까?\n저장된 모든 데이터(학번, 비밀번호)가 삭제됩니다.",
        view=view,
        ephemeral=True,
    )


class _WithdrawView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=60)
        self._user_id = user_id

    @discord.ui.button(label="탈퇴 확인", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("권한이 없습니다.", ephemeral=True)
            return

        db = get_session()
        try:
            user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
            if user:
                db.delete(user)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("탈퇴 처리 실패 (user=%s)", interaction.user.id)
            await interaction.response.send_message("탈퇴 처리 중 오류가 발생했습니다.", ephemeral=True)
            return
        finally:
            db.close()

        await interaction.response.send_message("✅ 탈퇴가 완료되었습니다. 모든 데이터가 삭제되었습니다.", ephemeral=True)
        from report import clear_dm
        await clear_dm(interaction.channel, interaction.client.user.id)

    @discord.ui.button(label="취소", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("탈퇴가 취소되었습니다.", ephemeral=True)


@client.event
async def on_message(message: discord.Message):
    if message.author.id == client.user.id:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return

    db = get_session()
    try:
        user = db.query(User).filter(User.discord_id == str(message.author.id)).first()
    finally:
        db.close()

    if not user:
        await message.channel.send(
            "안녕하세요! 🦒 세린이입니다.\n"
            "서비스를 이용하려면 `/가입`을 입력해주세요.\n"
            "전체 명령어는 `/도움말`로 확인할 수 있어요."
        )


@client.event
async def on_ready():
    global _ready_fired
    client.add_view(UpdateReportView())
    client.add_view(CheckApprovalView())

    await tree.sync()
    logger.info("슬래시 명령어 동기화 완료")
    logger.info("봇 로그인: %s", client.user)

    if not _ready_fired:
        _ready_fired = True
        for h, m in REPORT_TIMES:
            scheduler.add_job(send_report_to_all, "cron", hour=h, minute=m, args=[client])
        scheduler.start()
        logger.info("스케줄러 시작됨 (%s KST)", REPORT_SCHEDULE_TEXT)
        await send_report_to_all(client)


client.run(bot_settings.discord_token)
