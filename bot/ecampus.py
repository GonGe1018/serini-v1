from config import bot_settings


def ecampus_url(path: str) -> str:
    return f"{bot_settings.ecampus_base_url}/{path.lstrip('/')}"
