import os

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def required_environment(variable: str) -> str:
    raise ValueError(f"{variable} must be set")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = Field(
        default_factory=lambda: required_environment("MYSQL_USER")
    )
    mysql_password: str = Field(
        default_factory=lambda: required_environment("MYSQL_PASSWORD")
    )
    mysql_database: str = Field(
        default_factory=lambda: required_environment("MYSQL_DATABASE")
    )

    aes_secret_key: str = Field(
        default_factory=lambda: required_environment("AES_SECRET_KEY")
    )

    jwt_secret_key: str = Field(
        default_factory=lambda: required_environment("JWT_SECRET_KEY")
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    admin_username: str = Field(
        default_factory=lambda: required_environment("ADMIN_USERNAME")
    )
    admin_password: str = Field(
        default_factory=lambda: required_environment("ADMIN_PASSWORD")
    )

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator(
        "mysql_user",
        "mysql_password",
        "mysql_database",
        "jwt_secret_key",
        "admin_username",
        "admin_password",
    )
    @classmethod
    def reject_unsafe_values(cls, value: str, info: ValidationInfo) -> str:
        normalized = value.strip().lower()
        placeholders = {"changeme", "rootpassword", "serinipassword"}
        if (
            not normalized
            or normalized in placeholders
            or normalized.startswith(("your_", "change_me", "replace_me"))
        ):
            raise ValueError(f"{info.field_name} must be configured securely")
        return value

    @field_validator("aes_secret_key")
    @classmethod
    def validate_aes_key(cls, value: str) -> str:
        try:
            key = bytes.fromhex(value)
        except ValueError as error:
            raise ValueError("aes_secret_key must be hexadecimal") from error
        if len(key) != 32:
            raise ValueError("aes_secret_key must contain exactly 32 bytes")
        return value


settings = Settings()
