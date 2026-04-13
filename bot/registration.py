import discord
from datetime import datetime
from shared.database import get_session, User
from shared.crypto import encrypt
from report import clear_and_send

AGREE_TEXT = """
**⚠️ 개인정보 수집 및 이용 동의**

세린이 서비스를 이용하려면 아래 내용에 동의해야 합니다.

**수집 항목**
- 세종대학교 집현캠퍼스 포탈 아이디 (학번)
- 세종대학교 집현캠퍼스 포탈 비밀번호

**수집 목적**
- 집현캠퍼스 자동 로그인 및 과제 정보 조회

**보관 방식**
- 비밀번호는 암호화하여 저장됩니다.
- 단, 과제 조회 시 복호화하여 사용됩니다.

**보관 기간**
- 서비스 탈퇴 또는 관리자 삭제 시까지

위 내용에 동의하시면 ✅ 버튼을, 거부하시면 ❌ 버튼을 눌러주세요.
"""


class CheckApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="승인 확인", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="check_approval")
    async def check_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = "확인 중..."
        button.emoji = "⏳"
        button.disabled = True
        await interaction.response.edit_message(view=self)

        db = get_session()
        try:
            user = db.query(User).filter(User.discord_id == str(interaction.user.id)).first()
            if not user:
                await interaction.followup.send("가입 정보를 찾을 수 없습니다.")
                return
            if user.status == "approved":
                await clear_and_send(interaction.channel, interaction.user.id, interaction.client.user.id)
            elif user.status == "rejected":
                button.label = "승인 확인"
                button.emoji = "🔍"
                button.disabled = False
                await interaction.edit_original_response(
                    content="❌ 가입이 거절되었습니다. `!가입`으로 재신청할 수 있습니다.",
                    view=None,
                )
            else:
                button.label = "승인 확인"
                button.emoji = "🔍"
                button.disabled = False
                await interaction.edit_original_response(view=self)
        finally:
            db.close()


class RegistrationModal(discord.ui.Modal, title="세린이 회원가입"):
    ecampus_id = discord.ui.TextInput(
        label="집현캠퍼스 학번 (아이디)",
        placeholder="예: 20231234",
        required=True,
        max_length=50,
    )
    ecampus_pw = discord.ui.TextInput(
        label="집현캠퍼스 비밀번호",
        placeholder="비밀번호를 입력하세요",
        required=True,
        style=discord.TextStyle.short,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        ecampus_id = self.ecampus_id.value.strip()
        ecampus_pw = self.ecampus_pw.value.strip()
        ecampus_pw_enc = encrypt(ecampus_pw)
        agreed_at = datetime.utcnow()
        user = interaction.user

        db = get_session()
        try:
            existing = db.query(User).filter(User.discord_id == str(user.id)).first()
            if existing:
                if existing.status == "pending":
                    await interaction.response.send_message(
                        "이미 가입 신청이 접수되어 있습니다. 관리자 승인을 기다려주세요.",
                        view=CheckApprovalView(),
                    )
                elif existing.status == "approved":
                    await interaction.response.send_message("이미 승인된 계정입니다.")
                elif existing.status == "rejected":
                    existing.ecampus_id = ecampus_id
                    existing.ecampus_pw_enc = ecampus_pw_enc
                    existing.status = "pending"
                    existing.agreed_at = agreed_at
                    db.commit()
                    await interaction.response.send_message(
                        "재신청이 완료되었습니다. 관리자 승인을 기다려주세요.",
                        view=CheckApprovalView(),
                    )
                return

            new_user = User(
                discord_id=str(user.id),
                discord_username=str(user),
                ecampus_id=ecampus_id,
                ecampus_pw_enc=ecampus_pw_enc,
                status="pending",
                agreed_at=agreed_at,
            )
            db.add(new_user)
            db.commit()
            await interaction.response.send_message(
                "✅ 가입 신청이 완료되었습니다!\n관리자 승인 후 과제 알림 서비스가 시작됩니다.",
                view=CheckApprovalView(),
            )
        finally:
            db.close()


class AgreeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="동의", style=discord.ButtonStyle.success, emoji="✅")
    async def agree(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())

    @discord.ui.button(label="거부", style=discord.ButtonStyle.danger, emoji="❌")
    async def disagree(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "동의하지 않으셨습니다. 서비스를 이용하려면 동의가 필요합니다."
        )


async def registration_flow(message: discord.Message):
    view = AgreeView()
    await message.channel.send(AGREE_TEXT, view=view)
