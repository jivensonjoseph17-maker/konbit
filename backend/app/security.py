"""
Konbit — Sekirite: modpas ak token

Depandans:
    pip install "bcrypt>=4.0" "pyjwt>=2.8"

Poukisa bcrypt dirèk olye pou passlib: passlib 1.7.4 kase ak bcrypt 4.x.
Poukisa PyJWT olye python-jose: python-jose pa byen antretni ankò.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from .config import settings

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


# ---------------------------------------------------------------------------
# MODPAS
# ---------------------------------------------------------------------------

def _prehash(password: str) -> bytes:
    """
    bcrypt koupe nenpòt bagay pi long pase 72 bytes an silans.
    Nou pase modpas la nan sha256 avan pou tout longè konte.
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> list[str]:
    """Retounen lis pwoblèm yo. Lis vid = modpas la bon."""
    problems = []
    if len(password) < settings.password_min_length:
        problems.append(f"Modpas la dwe gen omwen {settings.password_min_length} karaktè.")
    if not any(c.isdigit() for c in password):
        problems.append("Modpas la dwe gen omwen yon chif.")
    if not any(c.isalpha() for c in password):
        problems.append("Modpas la dwe gen omwen yon lèt.")
    if password.lower() in {"motdepasse", "password", "12345678910", "konbit123"}:
        problems.append("Modpas sa a twò komen.")
    return problems


def generate_temp_password(length: int = 14) -> str:
    """Pou HR ki kreye yon kont pou yon nouvo anplwaye."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# TOKEN JWT
# ---------------------------------------------------------------------------

def _create_token(
    subject: str | int,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(
    user_id: int,
    role: str,
    organization_id: Optional[int] = None,
) -> str:
    """
    Nou mete role ak organization_id nan token an pou nou evite yon rekèt
    baz done sou chak apèl. ATANSYON: si HR chanje wòl yon moun, chanjman an
    ap pran efè sèlman lè token an ekspire (30 min pa defo).
    """
    return _create_token(
        subject=user_id,
        token_type=ACCESS_TOKEN,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims={"role": role, "org": organization_id},
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        subject=user_id,
        token_type=REFRESH_TOKEN,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str = ACCESS_TOKEN) -> Optional[dict[str, Any]]:
    """Retounen payload la, oswa None si token an pa valab."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except InvalidTokenError:
        return None

    if payload.get("type") != expected_type:
        return None
    if not payload.get("sub"):
        return None
    return payload