import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str
    mysql_password: str
    mysql_database: str

    aes_secret_key: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    admin_username: str
    admin_password: str

    discord_token: str = ""

    class Config:
        env_file = os.environ.get("ENV_FILE", ".env")


settings = Settings()
