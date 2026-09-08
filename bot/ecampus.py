from urllib.parse import urlsplit

from config import bot_settings


def ecampus_url(path: str) -> str:
    return f"{bot_settings.ecampus_base_url}/{path.lstrip('/')}"


def is_ecampus_url(url: str) -> bool:
    try:
        expected = urlsplit(bot_settings.ecampus_base_url)
        candidate = urlsplit(url)
        expected_port = expected.port or (443 if expected.scheme == "https" else 80)
        candidate_port = candidate.port or (443 if candidate.scheme == "https" else 80)
        return (
            candidate.scheme == expected.scheme
            and candidate.hostname == expected.hostname
            and candidate_port == expected_port
            and candidate.username is None
            and candidate.password is None
        )
    except ValueError:
        return False
