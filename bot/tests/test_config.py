from collections.abc import Mapping

import pytest
from config import BotSettings
from pydantic import ValidationError
from shared.config import Settings


def _valid_settings() -> Mapping[str, object]:
    return {
        "mysql_user": "serini",
        "mysql_password": "database-password",
        "mysql_database": "serini",
        "aes_secret_key": "01" * 32,
        "jwt_secret_key": "jwt-signing-secret",
        "admin_username": "operator",
        "admin_password": "admin-password",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mysql_password", ""),
        ("jwt_secret_key", "your_jwt_secret_here"),
        ("admin_password", "changeme"),
    ],
)
def test_settings_reject_empty_or_placeholder_secrets(
    field: str,
    value: str,
) -> None:
    values = dict(_valid_settings())
    values[field] = value

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_settings_reject_invalid_aes_key() -> None:
    values = dict(_valid_settings())
    values["aes_secret_key"] = "not-a-64-character-hex-key"

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


def test_bot_settings_reject_empty_discord_token() -> None:
    with pytest.raises(ValidationError):
        BotSettings(_env_file=None, discord_token="", **_valid_settings())


def test_operational_defaults_preserve_current_production_behavior() -> None:
    configured = BotSettings(
        _env_file=None,
        discord_token="discord-token",
        **_valid_settings(),
    )

    assert configured.ecampus_base_url == "https://ecampus.sejong.ac.kr"
    assert configured.timezone == "Asia/Seoul"
    assert configured.report_schedule == "08:00,13:00,21:00"
    assert configured.ecampus_timeout_ms == 30_000
    assert configured.dm_history_limit == 300
    assert configured.dm_delete_delay_seconds == 0.3
