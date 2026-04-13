import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from shared.config import settings
from shared.database import get_session, User
from registration import registration_flow, CheckApprovalView
from report import clear_and_send, send_report_to_all, UpdateReportView

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True
client = discord.Client(intents=intents)
scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


@client.event
async def on_message(message: discord.Message):
    if message.author.id == client.user.id:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return

    content = message.content.strip()

    if content == "!가입":
        await registration_flow(message)
    elif content == "!reset":
        db = get_session()
        try:
            user = db.query(User).filter(User.discord_id == str(message.author.id)).first()
            if not user or user.status != "approved":
                await message.channel.send("승인된 계정이 아닙니다.")
                return
        finally:
            db.close()
        await clear_and_send(message.channel, message.author.id, client.user.id)


@client.event
async def on_ready():
    client.add_view(UpdateReportView())
    client.add_view(CheckApprovalView())
    print(f"봇 로그인: {client.user}")
    scheduler.add_job(lambda: send_report_to_all(client), "cron", hour=8, minute=0)
    scheduler.add_job(lambda: send_report_to_all(client), "cron", hour=13, minute=0)
    scheduler.add_job(lambda: send_report_to_all(client), "cron", hour=21, minute=0)
    scheduler.start()
    print("스케줄러 시작됨 (08:00 / 13:00 / 21:00 KST)")
    await send_report_to_all(client)


client.run(settings.discord_token)
