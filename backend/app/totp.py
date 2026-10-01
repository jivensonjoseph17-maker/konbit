"""
Konbit — Kòd TOTP (Google Authenticator, Microsoft Authenticator…) ak kòd sekou
Chemen: backend/app/totp.py

  - Sekrè base32 (pyotp), kòd 6 chif chak 30 segonn.
  - matching_step(): aksepte ±1 fenèt (lè telefòn ki pa egzat), men JAMAN
    yon fenèt ki deja sèvi (last_step) — yon kòd pa ka sèvi 2 fwa.
  - Kòd sekou: "ABCD-EFGH", san 0/O ni 1/I; sha256 sèlman nan baz done a.
"""

import base64
import hashlib
import hmac
import io
import secrets
import time
from typing import Optional

import pyotp
import qrcode

STEP_SECONDS = 30
ISSUER = "KONMBIT"
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """otpauth://… — se sa kòd QR la genyen."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_png_data_uri(text: str) -> str:
    """Kòd QR an PNG, kòm data: URI (frontend lan mete l nan yon <img>)."""
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def matching_step(secret: str, code: str, last_step: Optional[int],
                  now: Optional[float] = None) -> Optional[int]:
    """Fenèt 30 s kòd la koresponn ak li, oswa None. Fenèt ≤ last_step refize."""
    digits = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(digits) != 6 or not secret:
        return None
    totp = pyotp.TOTP(secret)
    current = int((now if now is not None else time.time()) // STEP_SECONDS)
    for step in (current - 1, current, current + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), digits):
            return step
    return None


def new_recovery_codes(count: int = 10) -> list[str]:
    def part() -> str:
        return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4))
    return [f"{part()}-{part()}" for _ in range(count)]


def normalize_recovery(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def hash_recovery(code: str) -> str:
    return hashlib.sha256(normalize_recovery(code).encode("ascii", "ignore")).hexdigest()