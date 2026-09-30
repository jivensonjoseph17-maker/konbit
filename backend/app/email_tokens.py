"""
Konbit — Lyen pa imel (chanje modpas, verifye imel)
Chemen: backend/app/email_tokens.py

  - Nou sere sha256 lyen an SÈLMAN: si baz done a koule, lyen yo pa ka sèvi.
  - Yon lyen sèvi YON SÈL FWA, e li ekspire.
  - Yon nouvo lyen anile ansyen lyen ki poko sèvi yo (menm objektif).
  - Yon kont dezaktive pa ka sèvi ak yon lyen.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from .models import EmailToken, User

RESET = "reset"
VERIFY = "verify"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value) -> datetime:
    """SQLite retounen dat san fizo orè (oswa yon tèks): se UTC."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> str:
    """Kreye yon nouvo lyen epi retounen tèks li (pou imel la). Komite sesyon an."""
    now = _now()
    db.query(EmailToken).filter(
        EmailToken.user_id == user.id,
        EmailToken.purpose == purpose,
        EmailToken.used_at.is_(None),
    ).update({EmailToken.used_at: now}, synchronize_session=False)

    raw = secrets.token_urlsafe(32)
    db.add(EmailToken(
        user_id=user.id,
        purpose=purpose,
        token_hash=_hash(raw),
        expires_at=now + ttl,
        created_at=now,
    ))
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> Optional[User]:
    """
    Itilizatè a si lyen an valab (epi make l itilize), oswa None.
    PA komite: moun ki rele l la komite ak pwòp chanjman pa l yo.
    """
    tok = db.query(EmailToken).filter(
        EmailToken.token_hash == _hash(raw or ""),
        EmailToken.purpose == purpose,
    ).first()
    if tok is None or tok.used_at is not None or _aware(tok.expires_at) <= _now():
        return None

    user = db.query(User).filter(User.id == tok.user_id).first()
    if user is None or not user.is_active:
        return None

    tok.used_at = _now()
    return user