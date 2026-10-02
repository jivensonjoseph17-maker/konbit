"""
Konbit — Pwoteksyon koneksyon ak enskripsyon
Chemen: backend/app/login_guard.py

Twa règ, tout konte nan tab auth_attempts (pa nan memwa: yo mache menm
lè Render lanse plizyè kopi sèvè a):

  1. IMEL: settings.max_failed_logins move esè sou yon imel nan
     settings.login_window_minutes minit → imel sa a bloke jiskaske esè
     yo soti nan fenèt la. Sa aplike MENM pou yon imel ki pa egziste:
     repons lan idantik, kidonk yon atakè pa aprann ki kont ki reyèl.
     Yon koneksyon reyisi, oswa yon reset HR (unlock_login), efase kontè a.
  2. IP: settings.login_max_failures_per_ip move esè depi yon IP (sou
     nenpòt imel) nan menm fenèt la → IP sa a bloke.
  3. ENSKRIPSYON: settings.signup_max_per_ip_hour pa IP pa èdtan.

Pandan yon blokaj, esè yo PA ekri: sinon yon atakè ta ka kenbe yon kont
bloke pou tout tan (se sa ansyen règ la te fè ak failed_login_count).

IP: request.client.host. Dèyè Render, uvicorn --proxy-headers ranpli l ak
X-Forwarded-For. POU VERIFYE apre deplwaman: yon fo X-Forwarded-For pa
dwe chanje IP ki ekri nan jounal odit la.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import settings
from .models import AuthAttempt

LOGIN = "login"
SIGNUP = "signup"
KEEP_DAYS = 2


def client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value) -> Optional[datetime]:
    """SQLite retounen dat san fizo orè (oswa yon tèks): se UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _norm_email(email: Optional[str]) -> Optional[str]:
    email = (email or "").strip().lower()
    return email[:255] or None


def record_attempt(db: Session, kind: str, ip: Optional[str], email: Optional[str],
                   *, success: bool) -> None:
    """Ekri yon esè (reyisi oswa non). Komite sesyon an."""
    db.add(AuthAttempt(
        kind=kind,
        ip_address=ip[:45] if ip else None,
        email=_norm_email(email),
        success=success,
        created_at=_now(),
    ))
    # Netwayaj: anviwon 1 fwa sou 50, efase liy ki gen plis pase KEEP_DAYS jou.
    if secrets.randbelow(50) == 0:
        db.query(AuthAttempt).filter(
            AuthAttempt.created_at < _now() - timedelta(days=KEEP_DAYS),
        ).delete(synchronize_session=False)
    db.commit()


def email_locked(db: Session, email: Optional[str]) -> bool:
    """Twòp move esè sou imel sa a depi dènye koneksyon reyisi (oswa reset HR)."""
    email = _norm_email(email)
    if not email:
        return False
    since = _now() - timedelta(minutes=settings.login_window_minutes)
    last_ok = _aware(db.query(func.max(AuthAttempt.created_at)).filter(
        AuthAttempt.kind == LOGIN,
        AuthAttempt.email == email,
        AuthAttempt.success.is_(True),
    ).scalar())
    if last_ok is not None and last_ok > since:
        since = last_ok
    failures = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == LOGIN,
        AuthAttempt.email == email,
        AuthAttempt.success.is_(False),
        AuthAttempt.created_at > since,
    ).scalar() or 0
    return failures >= settings.max_failed_logins


def ip_blocked(db: Session, ip: Optional[str]) -> bool:
    if not ip:
        return False
    since = _now() - timedelta(minutes=settings.login_window_minutes)
    failures = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == LOGIN,
        AuthAttempt.ip_address == ip,
        AuthAttempt.success.is_(False),
        AuthAttempt.created_at > since,
    ).scalar() or 0
    return failures >= settings.login_max_failures_per_ip


def signup_blocked(db: Session, ip: Optional[str]) -> bool:
    if not ip:
        return False
    since = _now() - timedelta(hours=1)
    count = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == SIGNUP,
        AuthAttempt.ip_address == ip,
        AuthAttempt.created_at > since,
    ).scalar() or 0
    return count >= settings.signup_max_per_ip_hour


def unlock_login(db: Session, email: Optional[str]) -> None:
    """HR bay yon nouvo modpas oswa reaktive kont lan: blokaj la efase."""
    record_attempt(db, LOGIN, None, email, success=True)


# ---------------------------------------------------------------------------
# MWEN BLIYE MODPAS / VOYE LYEN VERIFIKASYON ANKÒ (routers/auth.py)
# Limit pa imel ak pa IP pa èdtan. Lè limit la rive, auth.py bay MENM
# repons lan san li pa voye imel (pa gen enimerasyon, pa gen spam).
# ---------------------------------------------------------------------------

RESET_REQUEST = "reset"


def reset_blocked(db: Session, ip: Optional[str], email: Optional[str]) -> bool:
    since = _now() - timedelta(hours=1)
    base = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == RESET_REQUEST,
        AuthAttempt.created_at > since,
    )
    email = _norm_email(email)
    if email and (base.filter(AuthAttempt.email == email).scalar() or 0) >= settings.reset_max_per_email_hour:
        return True
    if ip and (base.filter(AuthAttempt.ip_address == ip).scalar() or 0) >= settings.reset_max_per_ip_hour:
        return True
    return False


# ---------------------------------------------------------------------------
# KÒD 2FA (routers/mfa.py): menm règ ak modpas la — max_failed_logins move
# kòd nan fenèt la → 15 minit. Yon kòd ki bon efase kontè a.
# ---------------------------------------------------------------------------

MFA = "mfa"


def mfa_blocked(db: Session, email: Optional[str]) -> bool:
    email = _norm_email(email)
    if not email:
        return False
    since = _now() - timedelta(minutes=settings.login_window_minutes)
    last_ok = _aware(db.query(func.max(AuthAttempt.created_at)).filter(
        AuthAttempt.kind == MFA,
        AuthAttempt.email == email,
        AuthAttempt.success.is_(True),
    ).scalar())
    if last_ok is not None and last_ok > since:
        since = last_ok
    failures = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == MFA,
        AuthAttempt.email == email,
        AuthAttempt.success.is_(False),
        AuthAttempt.created_at > since,
    ).scalar() or 0
    return failures >= settings.max_failed_logins


# ---------------------------------------------------------------------------
# APLIKASYON PIBLIK (paj karyè a, routers/applications.py)
# ---------------------------------------------------------------------------

APPLY = "apply"


def apply_blocked(db: Session, ip: Optional[str], email: Optional[str]) -> bool:
    since = _now() - timedelta(hours=1)
    base = db.query(func.count(AuthAttempt.id)).filter(
        AuthAttempt.kind == APPLY,
        AuthAttempt.created_at > since,
    )
    email = _norm_email(email)
    if ip and (base.filter(AuthAttempt.ip_address == ip).scalar() or 0) >= settings.apply_max_per_ip_hour:
        return True
    if email and (base.filter(AuthAttempt.email == email).scalar() or 0) >= settings.apply_max_per_email_hour:
        return True
    return False
