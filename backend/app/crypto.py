"""
Konbit — Chifraj done sansib (kont labank, NIF/CIN, MonCash, sekrè 2FA)
Chemen: backend/app/crypto.py

KIJAN: Fernet (AES-128-CBC + HMAC-SHA256, bibliyotèk `cryptography`).
  - Chak valè gen pwòp vektè l: menm nimewo a bay yon rezilta diferan.
  - Si yon moun chanje yon sèl lèt nan baz done a, dechifraj la refize l.

KOLÒN: models.py sèvi ak EncryptedString(): li chifre lè done a ANTRE
nan baz done a, epi li dechifre lè l SOTI. Router yo pa wè diferans.
Valè chifre yo kòmanse ak "enc:v1:". Yon valè san mak sa a (ansyen done,
anvan migrasyon a1c3e5f7b9d2) li jan l ye.

LIMIT: baz done a pa ka CHÈCHE nan yon kolòn chifre (WHERE x = '…').

KLE: settings.data_encryption_key (DATA_ENCRYPTION_KEY).
  - Plizyè kle separe pa vigil = rotasyon: premye a chifre, tout yo dechifre.
  - Vid: kle devlopman ki soti nan SECRET_KEY. Refize nan pwodiksyon.
  - PÈDI KLE A = PÈDI DONE CHIFRE YO, menm nan backup yo.
"""

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.types import Text, TypeDecorator

from .config import settings

PREFIX = "enc:v1:"


def _dev_key(secret_key: str) -> str:
    digest = hashlib.sha256(("konbit-data-dev:" + secret_key).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def build_cipher(keys: str, secret_key: str, production: bool) -> MultiFernet:
    parts = [k.strip() for k in (keys or "").split(",") if k.strip()]
    if not parts:
        if production:
            raise RuntimeError("DATA_ENCRYPTION_KEY obligatwa nan pwodiksyon.")
        parts = [_dev_key(secret_key)]
    return MultiFernet([Fernet(k.encode("ascii")) for k in parts])


_cipher: Optional[MultiFernet] = None


def cipher() -> MultiFernet:
    global _cipher
    if _cipher is None:
        _cipher = build_cipher(settings.data_encryption_key, settings.secret_key, settings.is_production)
    return _cipher


def encrypt_value(value: Optional[str]) -> Optional[str]:
    """Toujou chifre (menm yon tèks ki sanble chifre deja: yon moun pa ka twonpe nou)."""
    if value is None or value == "":
        return value
    return PREFIX + cipher().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if value is None or not value.startswith(PREFIX):
        return value
    try:
        return cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Nou pa ka dechifre yon done sansib: DATA_ENCRYPTION_KEY la chanje oswa li manke."
        ) from exc


class EncryptedString(TypeDecorator):
    """Kolòn tèks ki chifre otomatikman (gade anlè)."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)