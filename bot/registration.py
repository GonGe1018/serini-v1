import logging
import discord
from datetime import datetime
from shared.database import get_session, User
from shared.crypto import encrypt
from report import clear_and_send

logger = logging.getLogger(__name__)

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

**주의 사항**
- 비밀번호는 암호화 후 저장되지만, 서비스 이용을 위해 중간중간 복호화 되어 런타임 메모리 상에 존재할 수 있습니다.
- 본 서비스를 사용하는 모든 사용자의 일정 크롤링은 동일 IP, 동일 기기에서 이루어집니다. 따라서 사용자가 여러 명일 경우에는 학교에서 의심 계정으로 판단하여 차단될 수 있습니다.
- 위의 사항에 대하여, 세린이 서비스는 어떠한 책임도 지지 않습니다. 사용자 본인의 판단 하에 동의 여부를 결정해주세요.

위 내용에 동의하시면 ✅ 버튼을, 거부하시면 ❌ 버튼을 눌러주세요.
"""


class CheckApprovalView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="승인 확인",
        style=discord.ButtonStyle.primary,
        emoji="🔍",
        custom_id="check_approval",
    )
    async def check_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        button.label = "확인 중..."
        button.emoji = "⏳"
        button.disabled = True
        await interaction.response.edit_message(view=self)

        db = get_session()
        try:
            user = (
                db.query(User)
                .filter(User.discord_id == str(interaction.user.id))
                .first()
            )
            if not user:
                await interaction.followup.send("가입 정보를 찾을 수 없습니다.")
                return
            if user.status == "approved":
                await clear_and_send(
                    interaction.channel, interaction.user.id, interaction.client.user.id
                )
            elif user.status == "rejected":
                await interaction.edit_original_response(
                    content="❌ 가입이 거절되었습니다. `!가입`으로 재신청할 수 있습니다.",
                    view=None,
                )
            else:
                button.label = "승인 확인"
                button.emoji = "🔍"
                button.disabled = False
                await interaction.edit_original_response(
                    content="⏳ 아직 승인 대기 중입니다. 잠시 후 다시 확인해주세요.",
                    view=self,
                )
        except Exception:
            logger.exception("승인 확인 중 오류 (user=%s)", interaction.user.id)
            await interaction.followup.send(
                "확인 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            )
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
        try:
            ecampus_id = self.ecampus_id.value.strip()
            ecampus_pw = self.ecampus_pw.value.strip()
            ecampus_pw_enc = encrypt(ecampus_pw)
            agreed_at = datetime.utcnow()
            user = interaction.user

            db = get_session()
            try:
                existing = (
                    db.query(User).filter(User.discord_id == str(user.id)).first()
                )
                if existing:
                    if existing.status == "pending":
                        await interaction.response.send_message(
                            "이미 가입 신청이 접수되어 있습니다. 관리자 승인을 기다려주세요.",
                            view=CheckApprovalView(),
                            ephemeral=True,
                        )
                    elif existing.status == "approved":
                        await interaction.response.send_message(
                            "이미 승인된 계정입니다.", ephemeral=True
                        )
                    elif existing.status == "rejected":
                        existing.ecampus_id = ecampus_id
                        existing.ecampus_pw_enc = ecampus_pw_enc
                        existing.status = "pending"
                        existing.agreed_at = agreed_at
                        db.commit()
                        await interaction.response.send_message(
                            "재신청이 완료되었습니다. 관리자 승인을 기다려주세요.",
                            view=CheckApprovalView(),
                            ephemeral=True,
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
                    ephemeral=True,
                )
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception:
            logger.exception("회원가입 처리 중 오류 (user=%s)", interaction.user.id)
            try:
                await interaction.response.send_message(
                    "가입 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                    ephemeral=True,
                )
            except Exception:
                pass


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
            "동의하지 않으셨습니다. 서비스를 이용하려면 동의가 필요합니다.",
            ephemeral=True,
        )


class PasswordChangeModal(discord.ui.Modal, title="비밀번호 변경"):
    new_password = discord.ui.TextInput(
        label="새 집현캠퍼스 비밀번호",
        placeholder="변경할 비밀번호를 입력하세요",
        required=True,
        style=discord.TextStyle.short,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            db = get_session()
            try:
                user = (
                    db.query(User)
                    .filter(User.discord_id == str(interaction.user.id))
                    .first()
                )
                if not user:
                    await interaction.response.send_message(
                        "가입 정보를 찾을 수 없습니다.", ephemeral=True
                    )
                    return
                user.ecampus_pw_enc = encrypt(self.new_password.value.strip())
                db.commit()
                await interaction.response.send_message(
                    "✅ 비밀번호가 변경되었습니다.", ephemeral=True
                )
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        except Exception:
            logger.exception("비밀번호 변경 실패 (user=%s)", interaction.user.id)
            try:
                await interaction.response.send_message(
                    "비밀번호 변경 중 오류가 발생했습니다.", ephemeral=True
                )
            except Exception:
                pass


async def registration_flow(interaction: discord.Interaction):
    view = AgreeView()
    await interaction.response.send_message(AGREE_TEXT, view=view, ephemeral=True)
