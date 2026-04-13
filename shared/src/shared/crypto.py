import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from shared.config import settings

_AAD = b"serini-ecampus-credential"


def _get_key() -> bytes:
    key = bytes.fromhex(settings.aes_secret_key)
    if len(key) != 32:
        raise ValueError("AES_SECRET_KEY must be 32 bytes (64 hex chars)")
    return key


def encrypt(plaintext: str) -> str:
    key = _get_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), _AAD)
    return base64.b64encode(nonce + ct).decode()


def decrypt(token: str) -> str:
    key = _get_key()
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, _AAD).decode()
