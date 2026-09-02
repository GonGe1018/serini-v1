from zoneinfo import ZoneInfo

from pydantic import Field, ValidationInfo, field_validator
from shared.config import Settings, required_environment


class BotSettings(Settings):
    discord_token: str = Field(
        default_factory=lambda: required_environment("DISCORD_TOKEN")
    )
    ecampus_base_url: str = "https://ecampus.sejong.ac.kr"
    timezone: str = "Asia/Seoul"
    report_schedule: str = "08:00,13:00,21:00"
    ecampus_timeout_ms: int = 30_000
    dm_history_limit: int = 300
    dm_delete_delay_seconds: float = 0.3

    @field_validator("discord_token")
    @classmethod
    def reject_unsafe_token(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or normalized.startswith(("your_", "change_me", "replace_me")):
            raise ValueError("discord_token must be configured securely")
        return value

    @field_validator("ecampus_base_url")
    @classmethod
    def normalize_ecampus_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("ecampus_base_url must be an HTTP URL")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except KeyError as error:
            raise ValueError("timezone must be a valid IANA timezone") from error
        return value

    @field_validator("report_schedule")
    @classmethod
    def validate_report_schedule(cls, value: str, info: ValidationInfo) -> str:
        entries = value.split(",")
        try:
            times = [tuple(int(part) for part in entry.split(":")) for entry in entries]
        except ValueError as error:
            raise ValueError("report_schedule must contain HH:MM entries") from error
        if not times or any(
            len(time) != 2 or not 0 <= time[0] <= 23 or not 0 <= time[1] <= 59
            for time in times
        ):
            raise ValueError(f"{info.field_name} must contain valid HH:MM entries")
        return value


bot_settings = BotSettings()
