"""
Konbit — Verifikasyon an 2 etap (TOTP)
Chemen: backend/app/routers/mfa.py   (prefix /api/auth/mfa)

    GET  /status               Estati 2FA kont mwen
    POST /setup                Kòmanse (modpas obligatwa): sekrè + kòd QR
    POST /enable               Konfime ak yon kòd → kòd sekou yo (YON SÈL FWA) + nouvo token
    POST /disable              Dezaktive (modpas + kòd) — PA pou admin/HR
    POST /recovery-codes       Nouvo kòd sekou (modpas) — ansyen yo anile
    POST /verify               Etap 2 koneksyon an: mfa_token + kòd → token yo
    POST /reset/{employee_id}  Administratè a efase 2FA yon anplwaye (telefòn pèdi)

KONEKSYON: si 2FA aktive, /api/auth/login pa bay token: li bay yon
mfa_token (5 minit, kalite "mfa") ki sèvi SÈLMAN pou /verify.

OBLIGATWA pou deps.MFA_REQUIRED_ROLES (org_admin, hr, super_admin) lè
deps.ENFORCE_MFA = True: san li, lòt endpoint yo refize (403).

ATANSYON: totp_secret poko chifre — pati D (chifraj) ap kouvri l.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import MFA_REQUIRED_ROLES, CurrentUser, DbSession, TenantId, require_admin
from ..login_guard import MFA, client_ip, mfa_blocked, record_attempt
from ..models import AuditLog, Employee, RecoveryCode, User
from ..schemas import Message, TokenPair
from ..security import MFA_TOKEN, decode_token, token_version_of, verify_password
from ..totp import (
    hash_recovery,
    matching_step,
    new_recovery_codes,
    new_secret,
    provisioning_uri,
    qr_png_data_uri,
)
from .auth import _issue_tokens

logger = logging.getLogger("konbit")

router = APIRouter()

BAD_CODE = "Kòd la pa bon. Eseye ankò."


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(db: Session, request: Request, user: User, action: str,
           entity_id: Optional[int] = None, org_id: Optional[int] = None) -> None:
    try:
        db.add(AuditLog(
            organization_id=org_id if org_id is not None else user.organization_id,
            user_id=user.id, action=action, entity_type="user",
            entity_id=entity_id if entity_id is not None else user.id,
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Modpas aktyèl la pa kòrèk.")


def _codes_left(db: Session, user: User) -> int:
    return db.query(RecoveryCode).filter(
        RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None),
    ).count()


def _replace_codes(db: Session, user: User) -> list[str]:
    """Nouvo kòd sekou (ansyen yo efase). PA komite."""
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete(synchronize_session=False)
    codes = new_recovery_codes()
    now = _now()
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_recovery(code), created_at=now))
    return codes


def _clear_mfa(db: Session, user: User) -> None:
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = None
    db.query(RecoveryCode).filter(RecoveryCode.user_id == user.id).delete(synchronize_session=False)


def _check_second_factor(db: Session, user: User, code: str) -> bool:
    """Kòd TOTP oswa kòd sekou. Si li bon, li make l itilize. PA komite."""
    step = matching_step(user.totp_secret, code, user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return True
    recovery = db.query(RecoveryCode).filter(
        RecoveryCode.user_id == user.id,
        RecoveryCode.code_hash == hash_recovery(code),
        RecoveryCode.used_at.is_(None),
    ).first()
    if recovery is not None:
        recovery.used_at = _now()
        return True
    return False


# ---------------------------------------------------------------------------
# ESTATI AK KONFIGIRASYON
# ---------------------------------------------------------------------------

class MfaStatus(BaseModel):
    enabled: bool
    required: bool
    recovery_codes_left: int


@router.get("/status", response_model=MfaStatus)
def mfa_status(user: CurrentUser, db: DbSession):
    return MfaStatus(
        enabled=bool(user.totp_enabled),
        required=user.role in MFA_REQUIRED_ROLES,
        recovery_codes_left=_codes_left(db, user) if user.totp_enabled else 0,
    )


class PasswordConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class MfaSetup(BaseModel):
    secret: str            # pou moun ki pa ka eskane kòd QR la
    otpauth_uri: str
    qr_png: str            # data:image/png;base64,…


@router.post("/setup", response_model=MfaSetup)
def mfa_setup(payload: PasswordConfirm, user: CurrentUser, db: DbSession):
    """Nouvo sekrè (poko aktif). Modpas obligatwa: yon sesyon vòlè pa ka mete pwòp telefòn li."""
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Verifikasyon an 2 etap deja aktive.")
    _check_password(user, payload.password)

    secret = new_secret()
    user.totp_secret = secret
    user.totp_last_step = None
    db.commit()

    uri = provisioning_uri(secret, user.email)
    return MfaSetup(secret=secret, otpauth_uri=uri, qr_png=qr_png_data_uri(uri))


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class EnableResult(TokenPair):
    codes: list[str]       # kòd sekou yo — parèt YON SÈL FWA


@router.post("/enable", response_model=EnableResult)
def mfa_enable(payload: CodeRequest, user: CurrentUser, request: Request, db: DbSession):
    if user.totp_enabled:
        raise HTTPException(status_code=409, detail="Verifikasyon an 2 etap deja aktive.")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="Kòmanse konfigirasyon an anvan.")

    step = matching_step(user.totp_secret, payload.code, None)
    if step is None:
        raise HTTPException(status_code=400, detail="Kòd la pa bon. Verifye lè telefòn ou.")

    user.totp_enabled = True
    user.totp_last_step = step
    # Tout lòt sesyon yo (ak yon moun ki te ka vòlè youn) sispann mache.
    user.token_version = (user.token_version or 0) + 1
    codes = _replace_codes(db, user)
    db.commit()
    db.refresh(user)
    _audit(db, request, user, "mfa_enable")
    return EnableResult(codes=codes, **_issue_tokens(user).model_dump())


class DisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=20)


@router.post("/disable", response_model=Message)
def mfa_disable(payload: DisableRequest, user: CurrentUser, request: Request, db: DbSession):
    if user.role in MFA_REQUIRED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Wòl ou mande verifikasyon an 2 etap: ou pa ka dezaktive l.",
        )
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="Verifikasyon an 2 etap pa aktive.")
    _check_password(user, payload.password)
    if not _check_second_factor(db, user, payload.code):
        raise HTTPException(status_code=400, detail=BAD_CODE)

    _clear_mfa(db, user)
    db.commit()
    _audit(db, request, user, "mfa_disable")
    return Message(detail="Verifikasyon an 2 etap dezaktive.")


class RecoveryCodesOut(BaseModel):
    codes: list[str]


@router.post("/recovery-codes", response_model=RecoveryCodesOut)
def mfa_new_recovery_codes(payload: PasswordConfirm, user: CurrentUser, request: Request, db: DbSession):
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="Verifikasyon an 2 etap pa aktive.")
    _check_password(user, payload.password)
    codes = _replace_codes(db, user)
    db.commit()
    _audit(db, request, user, "mfa_recovery_codes")
    return RecoveryCodesOut(codes=codes)


# ---------------------------------------------------------------------------
# ETAP 2 KONEKSYON AN
# ---------------------------------------------------------------------------

class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=20, max_length=4000)
    code: str = Field(min_length=6, max_length=20)


@router.post("/verify", response_model=TokenPair)
def mfa_verify(payload: MfaVerifyRequest, request: Request, db: DbSession):
    expired = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sesyon koneksyon an ekspire. Konekte ankò.",
    )
    data = decode_token(payload.mfa_token, expected_type=MFA_TOKEN)
    if data is None:
        raise expired
    user = db.query(User).filter(User.id == int(data["sub"])).first()
    if (user is None or not user.is_active or not user.totp_enabled
            or token_version_of(data) != (user.token_version or 0)):
        raise expired

    if mfa_blocked(db, user.email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Twòp esè. Tann kèk minit.")

    ip = client_ip(request)
    if not _check_second_factor(db, user, payload.code):
        record_attempt(db, MFA, ip, user.email, success=False)
        _audit(db, request, user, "mfa_failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CODE)

    user.last_login_at = _now()
    record_attempt(db, MFA, ip, user.email, success=True)     # komite last_step tou
    _audit(db, request, user, "login")
    return _issue_tokens(user)


# ---------------------------------------------------------------------------
# ADMINISTRATÈ A: TELEFÒN PÈDI
# ---------------------------------------------------------------------------

@router.post("/reset/{employee_id}", response_model=Message, dependencies=[Depends(require_admin)])
def mfa_reset_employee(employee_id: int, user: CurrentUser, org_id: TenantId,
                       request: Request, db: DbSession):
    """
    Efase 2FA yon moun ki pèdi telefòn li AK kòd sekou li yo. Administratè
    biznis la sèlman (pa HR), jamè pou pwòp kont li. Tout sesyon moun nan anile.
    """
    emp = db.query(Employee).filter(
        Employee.id == employee_id, Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    if not emp.user_id:
        raise HTTPException(status_code=400, detail="Anplwaye a pa gen kont koneksyon.")
    login = db.query(User).filter(User.id == emp.user_id, User.organization_id == org_id).first()
    if login is None:
        raise HTTPException(status_code=404, detail="Kont koneksyon an pa jwenn.")
    if login.id == user.id:
        raise HTTPException(status_code=403, detail="Ou pa ka reyinisyalize pwòp verifikasyon ou.")

    _clear_mfa(db, login)
    login.token_version = (login.token_version or 0) + 1
    db.commit()
    _audit(db, request, user, "mfa_reset", entity_id=login.id, org_id=org_id)
    return Message(detail="Verifikasyon an 2 etap efase. Moun nan ap konfigire l ankò.")