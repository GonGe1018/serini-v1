from urllib.parse import urlsplit

from ecampus import ecampus_url, is_ecampus_url


def test_is_ecampus_url_accepts_configured_origin_only() -> None:
    # Given
    allowed = ecampus_url("/mod/quiz/view.php?id=1")
    configured = urlsplit(allowed)
    external = f"{configured.scheme}://attacker.example/mod/quiz/view.php?id=1"
    userinfo = (
        f"{configured.scheme}://user@{configured.hostname}/mod/quiz/view.php?id=1"
    )
    alternate_port = (
        f"{configured.scheme}://{configured.hostname}:444/mod/quiz/view.php?id=1"
    )
    malformed = "https://[::1"

    # When
    results = [
        is_ecampus_url(url)
        for url in (allowed, external, userinfo, alternate_port, malformed)
    ]

    # Then
    assert results == [True, False, False, False, False]
