"""
Konbit — Router Kiyòsk (pwentaj sou tablèt / òdinatè biznis la ak kòd pèsonèl)
Chemen: backend/app/routers/kiosk.py

Administrasyon (kont konekte):
    GET    /api/kiosk/settings                 Mòd pwentaj + mòd kòd (tout anplwaye)
    PUT    /api/kiosk/settings                 Chanje yo (admin)
    GET    /api/kiosk/devices                  Tablèt yo (admin)
    POST   /api/kiosk/devices                  Aktive yon tablèt → token long (yon sèl fwa)
    POST   /api/kiosk/pairings                 Kòd kout 6 karaktè pou aktive yon tablèt (admin)
    DELETE /api/kiosk/devices/{id}             Dezaktive yon tablèt (admin)
    POST   /api/kiosk/employees/{id}/pin       Bay / rejenere kòd yon anplwaye

Tablèt la, san koneksyon:
    POST   /api/kiosk/pair                     Kòd kout la → token tablèt la

Tablèt la (header X-Kiosk-Token, PA token itilizatè):
    GET    /api/kiosk/device                   Non tablèt la, biznis la (logo, adrès), mòd kòd la
    POST   /api/kiosk/device/deactivate        Dekonekte tablèt la (token an pa mache ankò)
    POST   /api/kiosk/identify                 Etap 1: kòd (± nimewo) → prenon, foto, antre/sòti
    POST   /api/kiosk/punch                    Etap 2: Antre / Sòti

MÒD KÒD (organizations.kiosk_pin_mode):
  - "number_pin": nimewo anplwaye + kòd (pa defo, pi sekirize).
  - "pin_only":   kòd 6 chif sèlman (tankou Legion). Pou jwenn moun nan san
    teste chak kòd PBKDF2 (twò lan), chak kòd gen yon kle rechèch HMAC
    (employees.kiosk_pin_lookup) ki kalkile ak kle sekrè sèvè a. Chak kòd
    INIK nan biznis la. Yon ansyen kòd san kle rechèch jwenn li otomatikman
    premye fwa moun nan pwente ak nimewo + kòd.

SEKIRITE:
  - Token tablèt la ak kòd yo pa janm estoke an klè (sha256 / PBKDF2 / HMAC).
    Kòd la parèt YON SÈL FWA, lè admin/manadjè a jenere l.
  - Token tablèt la pa ka fè anyen lòt pase pwentaj: se pa yon kont itilizatè.
  - 5 move kòd pou yon anplwaye → kòd li bloke 15 minit.
    20 move esè sou yon tablèt → tablèt la bloke 10 minit. /identify konte tou.
  - Menm mesaj erè pou "nimewo sa a pa egziste" ak "move kòd".
  - Etap 2 a montre FOTO moun nan: manadjè a wè si se pa li ki devan tablèt la.
  - Kòd kout aktivasyon: 6 karaktè, 10 minit, yon sèl fwa. 10 move esè
    pou yon adrès IP → bloke 10 minit.
  - Kòd, tablèt, mòd, blokaj: tout ale nan jounal odit la.
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..clock_mode import PHONE, get_clock_mode
from ..config import settings
from ..deps import (
    FORBIDDEN_ERROR,
    CurrentUser,
    DbSession,
    TenantId,
    is_in_management_chain,
    require_admin,
)
from ..models import (
    AttendanceStatus,
    AuditLog,
    Employee,
    EmploymentStatus,
    KioskDevice,
    KioskPairing,
    Organization,
    TimeEntry,
    User,
    UserRole,
)
from .attendance import (
    MAX_SHIFT_MINUTES,
    _as_aware,
    _compute_minutes,
    _now,
    _open_entry_for,
    _org_tz,
)
from .employee_photos import photo_url_for
from .org_logo import logo_url_for

router = APIRouter()

HR_ROLES = (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)

PIN_LENGTH = 6
MAX_PIN_FAILURES = 5
PIN_LOCK = timedelta(minutes=15)
MAX_DEVICE_FAILURES = 20
DEVICE_LOCK = timedelta(minutes=10)
_PBKDF2_ITERATIONS = 120_000

NUMBER_PIN = "number_pin"
PIN_ONLY = "pin_only"

_WEAK_PINS = {d * PIN_LENGTH for d in "0123456789"} | {
    "123456", "654321", "012345", "123123", "121212", "112233",
}

# Kòd kout aktivasyon: san O/0, I/1/L pou pèsonn pa konfonn yo.
PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIR_LENGTH = 6
PAIR_TTL = timedelta(minutes=10)
MAX_PAIR_FAILURES = 10
PAIR_WINDOW = timedelta(minutes=10)
# Move esè pa adrès IP. An memwa: chak pwosesis uvicorn gen pa l (ase pou
# 10 minit ak yon kòd ki mache yon sèl fwa). Tès yo vide l.
_PAIR_FAILURES: dict[str, list[datetime]] = {}

NOT_ACTIVATED = "Tablèt sa a pa aktive."
BAD_PAIR_CODE = "Kòd la pa bon oswa li ekspire."
BAD_CREDENTIALS = "Nimewo oswa kòd la pa bon."


# ---------------------------------------------------------------------------
# ZOUTI: KÒD, TOKEN, ODIT
# ---------------------------------------------------------------------------

def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), bytes.fromhex(salt_hex), int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def pin_lookup(org_id: int, pin: str) -> str:
    """Kle rechèch pou mòd "kòd sèlman": HMAC ak kle sekrè sèvè a, pa biznis."""
    return hmac.new(settings.kiosk_key.encode(), f"{org_id}:{pin}".encode(),
                    hashlib.sha256).hexdigest()


def _new_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"
        if pin not in _WEAK_PINS:
            return pin


def _lookup_taken(db: Session, org_id: int, lookup: str, except_id: int) -> bool:
    return db.query(Employee.id).filter(
        Employee.organization_id == org_id,
        Employee.kiosk_pin_lookup == lookup,
        Employee.id != except_id,
    ).first() is not None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _audit(db: Session, request: Request, org_id: int, user_id: Optional[int],
           action: str, entity_type: str, entity_id: Optional[int],
           changes: Optional[str] = None) -> None:
    db.add(AuditLog(
        organization_id=org_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()


def _digits(value: str) -> str:
    """'KB-0007' → '7'. Pou anplwaye a ka tape sèlman chif yo."""
    d = re.sub(r"\D", "", value or "")
    return d.lstrip("0") or ("0" if d else "")


def _find_employee(db: Session, org_id: int, number: str) -> Optional[Employee]:
    """Nimewo egzak (KB-0007) oswa sèlman chif yo (7, 0007). Yon sèl moun, sinon None."""
    raw = number.strip().upper()
    candidates = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.kiosk_pin_hash.isnot(None),
    ).all()

    exact = [e for e in candidates if (e.employee_number or "").upper() == raw]
    if len(exact) == 1:
        return exact[0]

    digits = _digits(raw)
    if not digits:
        return None
    matches = [e for e in candidates if _digits(e.employee_number) == digits]
    return matches[0] if len(matches) == 1 else None


def _find_by_pin(db: Session, org_id: int, pin: str) -> Optional[Employee]:
    """Mòd "kòd sèlman": kle rechèch la; yon sèl moun, sinon None."""
    matches = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.kiosk_pin_hash.isnot(None),
        Employee.kiosk_pin_lookup == pin_lookup(org_id, pin),
    ).all()
    return matches[0] if len(matches) == 1 else None


def get_pin_mode(db: Session, org_id: int) -> str:
    org = db.get(Organization, org_id)
    mode = getattr(org, "kiosk_pin_mode", None) or NUMBER_PIN
    return mode if mode in (NUMBER_PIN, PIN_ONLY) else NUMBER_PIN


def _pins_need_reset(db: Session, org_id: int) -> int:
    """Moun ki gen yon kòd men ki poko ka pwente an mòd "kòd sèlman"."""
    return db.query(func.count(Employee.id)).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.kiosk_pin_hash.isnot(None),
        Employee.kiosk_pin_lookup.is_(None),
    ).scalar() or 0


# ---------------------------------------------------------------------------
# TABLÈT LA (header X-Kiosk-Token)
# ---------------------------------------------------------------------------

def get_kiosk_device(
    db: DbSession,
    x_kiosk_token: Annotated[Optional[str], Header()] = None,
) -> KioskDevice:
    if not x_kiosk_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=NOT_ACTIVATED)
    device = db.query(KioskDevice).filter(
        KioskDevice.token_hash == _token_hash(x_kiosk_token),
        KioskDevice.is_active.is_(True),
    ).first()
    if device is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=NOT_ACTIVATED)
    org = db.get(Organization, device.organization_id)
    if org is None or not org.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=NOT_ACTIVATED)
    return device


KioskDeviceDep = Annotated[KioskDevice, Depends(get_kiosk_device)]


# ---------------------------------------------------------------------------
# MÒD PWENTAJ AK MÒD KÒD
# ---------------------------------------------------------------------------

class ClockSettings(BaseModel):
    clock_mode: Literal["phone", "kiosk", "both"]
    pin_mode: Optional[Literal["number_pin", "pin_only"]] = None


class ClockSettingsOut(BaseModel):
    clock_mode: Literal["phone", "kiosk", "both"]
    pin_mode: Literal["number_pin", "pin_only"]
    pins_need_reset: int = 0        # kòd ki poko mache an mòd "kòd sèlman"


def _settings_out(db: Session, org_id: int) -> ClockSettingsOut:
    return ClockSettingsOut(clock_mode=get_clock_mode(db, org_id),
                            pin_mode=get_pin_mode(db, org_id),
                            pins_need_reset=_pins_need_reset(db, org_id))


@router.get("/settings", response_model=ClockSettingsOut)
def read_settings(org_id: TenantId, db: DbSession):
    """Tout anplwaye ka li l: tablo de bò a kache bouton Klòk in lan si mòd la se 'kiosk'."""
    return _settings_out(db, org_id)


@router.put("/settings", response_model=ClockSettingsOut, dependencies=[Depends(require_admin)])
def update_settings(payload: ClockSettings, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    org = db.get(Organization, org_id)
    before = get_clock_mode(db, org_id)
    before_pin = get_pin_mode(db, org_id)
    org.clock_mode = payload.clock_mode
    if payload.pin_mode is not None:
        org.kiosk_pin_mode = payload.pin_mode
    db.commit()
    changes = f"clock_mode: {before} -> {payload.clock_mode}"
    if payload.pin_mode is not None and payload.pin_mode != before_pin:
        changes += f"; kiosk_pin_mode: {before_pin} -> {payload.pin_mode}"
    _audit(db, request, org_id, user.id, "update", "organization", org_id, changes)
    return _settings_out(db, org_id)


# ---------------------------------------------------------------------------
# TABLÈT YO (admin)
# ---------------------------------------------------------------------------

class DeviceOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    name: str
    is_active: bool
    created_at: datetime
    last_seen_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class DeviceList(BaseModel):
    items: list[DeviceOut]


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class DeviceActivated(BaseModel):
    device: DeviceOut
    token: str                      # parèt YON SÈL FWA


@router.get("/devices", response_model=DeviceList, dependencies=[Depends(require_admin)])
def list_devices(org_id: TenantId, db: DbSession):
    rows = db.query(KioskDevice).filter(
        KioskDevice.organization_id == org_id,
    ).order_by(KioskDevice.created_at.desc()).all()
    return DeviceList(items=[DeviceOut.model_validate(d) for d in rows])


@router.post(
    "/devices",
    response_model=DeviceActivated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def activate_device(payload: DeviceCreate, user: CurrentUser, org_id: TenantId,
                    request: Request, response: Response, db: DbSession):
    token = "kk_" + secrets.token_urlsafe(32)
    device = KioskDevice(
        organization_id=org_id,
        name=payload.name.strip(),
        token_hash=_token_hash(token),
        created_by_id=user.id,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    _audit(db, request, org_id, user.id, "activate", "kiosk_device", device.id,
           f"Tablèt: {device.name}")
    response.headers["Cache-Control"] = "no-store"
    return DeviceActivated(device=DeviceOut.model_validate(device), token=token)


@router.delete("/devices/{device_id}", response_model=DeviceOut,
               dependencies=[Depends(require_admin)])
def revoke_device(device_id: int, user: CurrentUser, org_id: TenantId,
                  request: Request, db: DbSession):
    device = db.query(KioskDevice).filter(
        KioskDevice.id == device_id,
        KioskDevice.organization_id == org_id,
    ).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Tablèt la pa jwenn.")
    if device.is_active:
        device.is_active = False
        device.revoked_at = datetime.now(timezone.utc)
        db.commit()
        _audit(db, request, org_id, user.id, "revoke", "kiosk_device", device.id,
               f"Tablèt: {device.name}")
    db.refresh(device)
    return DeviceOut.model_validate(device)


# ---------------------------------------------------------------------------
# KÒD KOUT AKTIVASYON (6 karaktè, 10 minit, yon sèl fwa)
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    """'k7p-4qx' → 'K7P4QX'."""
    return re.sub(r"[^A-Z0-9]", "", (code or "").upper())


def _new_pair_code() -> str:
    return "".join(secrets.choice(PAIR_ALPHABET) for _ in range(PAIR_LENGTH))


def _format_code(code: str) -> str:
    return f"{code[:3]}-{code[3:]}"


def _pair_blocked(ip: str, now: datetime) -> bool:
    recent = [t for t in _PAIR_FAILURES.get(ip, []) if now - t < PAIR_WINDOW]
    _PAIR_FAILURES[ip] = recent
    return len(recent) >= MAX_PAIR_FAILURES


class PairingCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class PairingIssued(BaseModel):
    code: str                       # "K7P-4QX" — parèt YON SÈL FWA
    name: str
    expires_at: datetime


@router.post(
    "/pairings",
    response_model=PairingIssued,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_pairing(payload: PairingCreate, user: CurrentUser, org_id: TenantId,
                   request: Request, response: Response, db: DbSession):
    now = _now()
    expires_at = now + PAIR_TTL
    # Evite de kòd aktif idantik (chans lan piti anpil, men nou verifye).
    for _ in range(5):
        code = _new_pair_code()
        code_hash = _token_hash(code)
        clash = db.query(KioskPairing).filter(
            KioskPairing.code_hash == code_hash,
            KioskPairing.used_at.is_(None),
        ).all()
        if not any(_as_aware(p.expires_at) > now for p in clash):
            break

    pairing = KioskPairing(
        organization_id=org_id,
        name=payload.name.strip(),
        code_hash=code_hash,
        created_by_id=user.id,
        expires_at=expires_at,
    )
    db.add(pairing)
    db.commit()
    db.refresh(pairing)
    _audit(db, request, org_id, user.id, "pairing_create", "kiosk_pairing", pairing.id,
           f"Tablèt: {pairing.name} (kòd la pa ekri isit)")
    response.headers["Cache-Control"] = "no-store"
    return PairingIssued(code=_format_code(code), name=pairing.name, expires_at=expires_at)


class PairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class PairResult(BaseModel):
    token: str
    device_name: str
    organization_name: str


@router.post("/pair", response_model=PairResult)
def pair_device(payload: PairRequest, request: Request, response: Response, db: DbSession):
    """Tablèt la voye kòd kout la; li resevwa pwòp token pa l. Pa bezwen koneksyon."""
    now = _now()
    ip = request.client.host if request.client else "?"
    if _pair_blocked(ip, now):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Twòp esè. Tann kèk minit.")

    code = _normalize_code(payload.code)
    pairing = None
    if len(code) == PAIR_LENGTH:
        pairing = db.query(KioskPairing).filter(
            KioskPairing.code_hash == _token_hash(code),
            KioskPairing.used_at.is_(None),
        ).first()

    org = db.get(Organization, pairing.organization_id) if pairing is not None else None
    if (pairing is None or _as_aware(pairing.expires_at) <= now
            or org is None or not org.is_active):
        _PAIR_FAILURES.setdefault(ip, []).append(now)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=BAD_PAIR_CODE)

    # Yon sèl fwa, menm si de tablèt voye menm kòd la an menm tan.
    claimed = db.query(KioskPairing).filter(
        KioskPairing.id == pairing.id,
        KioskPairing.used_at.is_(None),
    ).update({KioskPairing.used_at: now}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=BAD_PAIR_CODE)

    token = "kk_" + secrets.token_urlsafe(32)
    device = KioskDevice(
        organization_id=pairing.organization_id,
        name=pairing.name,
        token_hash=_token_hash(token),
        created_by_id=pairing.created_by_id,
        last_seen_at=now,
    )
    db.add(device)
    db.flush()
    pairing.device_id = device.id
    db.commit()
    db.refresh(device)

    _audit(db, request, org.id, pairing.created_by_id, "activate", "kiosk_device", device.id,
           f"Tablèt: {device.name} (kòd kout #{pairing.id})")
    response.headers["Cache-Control"] = "no-store"
    return PairResult(token=token, device_name=device.name, organization_name=org.name)


# ---------------------------------------------------------------------------
# KÒD ANPLWAYE
# ---------------------------------------------------------------------------

class PinIssued(BaseModel):
    employee_id: int
    employee_number: str
    pin: str                        # parèt YON SÈL FWA
    set_at: datetime


@router.post("/employees/{employee_id}/pin", response_model=PinIssued)
def issue_pin(employee_id: int, user: CurrentUser, org_id: TenantId,
              request: Request, response: Response, db: DbSession):
    """
    HR/admin: pou nenpòt moun nan biznis la.
    Manadjè: pou tèt li ak moun ki anba l nan òganigram lan.
    Yon nouvo kòd ranplase ansyen an epi debloke kòd la si l te bloke.
    Kòd la INIK nan biznis la (mòd "kòd sèlman" bezwen sa).
    """
    target = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
    ).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")

    if user.role not in HR_ROLES:
        if user.role != UserRole.MANAGER:
            raise FORBIDDEN_ERROR
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None or not (
            viewer.id == target.id or is_in_management_chain(viewer, target)
        ):
            raise FORBIDDEN_ERROR

    for _ in range(50):
        pin = _new_pin()
        lookup = pin_lookup(org_id, pin)
        if not _lookup_taken(db, org_id, lookup, target.id):
            break
    else:                                   # 50 fwa menm kòd: pa ka rive an pratik
        raise HTTPException(status_code=500, detail="Yon erè entèn rive.")

    now = datetime.now(timezone.utc)
    target.kiosk_pin_hash = hash_pin(pin)
    target.kiosk_pin_lookup = lookup
    target.kiosk_pin_set_at = now
    target.kiosk_failed_count = 0
    target.kiosk_locked_until = None
    db.commit()

    # Kòd la li menm PA JANM ekri nan jounal la.
    _audit(db, request, org_id, user.id, "kiosk_pin_set", "employee", target.id,
           "Nouvo kòd kiyòsk jenere.")
    response.headers["Cache-Control"] = "no-store"
    return PinIssued(employee_id=target.id, employee_number=target.employee_number,
                     pin=pin, set_at=now)


# ---------------------------------------------------------------------------
# TABLÈT LA: ENFÒMASYON
# ---------------------------------------------------------------------------

class DeviceInfo(BaseModel):
    device_name: str
    organization_name: str
    organization_logo_url: Optional[str] = None
    organization_address: Optional[str] = None
    clock_mode: str
    pin_mode: str = NUMBER_PIN
    activated_by: Optional[str] = None     # non administratè ki aktive tablèt la


@router.get("/device", response_model=DeviceInfo)
def device_info(device: KioskDeviceDep, db: DbSession):
    org = db.get(Organization, device.organization_id)
    creator = db.get(User, device.created_by_id) if device.created_by_id else None
    device.last_seen_at = _now()
    db.commit()
    address = ", ".join(p for p in (org.address, org.city) if p) or None
    return DeviceInfo(device_name=device.name, organization_name=org.name,
                      organization_logo_url=logo_url_for(db, org),
                      organization_address=address,
                      clock_mode=get_clock_mode(db, device.organization_id),
                      pin_mode=get_pin_mode(db, device.organization_id),
                      activated_by=creator.full_name if creator else None)


@router.post("/device/deactivate", response_model=DeviceOut)
def deactivate_this_device(device: KioskDeviceDep, request: Request, db: DbSession):
    """
    Bouton "Dekonekte tablèt la" sou tablèt la li menm. Nou dezaktive tablèt la
    sou sèvè a (pa sèlman sou aparèy la): token an pa ka sèvi ankò, menm si
    yon moun te kopye l. Pou reyitilize l: yon nouvo kòd aktivasyon.
    """
    device.is_active = False
    device.revoked_at = _now()
    db.commit()
    _audit(db, request, device.organization_id, None, "revoke", "kiosk_device", device.id,
           f"Tablèt: {device.name} (dekonekte sou tablèt la)")
    db.refresh(device)
    return DeviceOut.model_validate(device)


# ---------------------------------------------------------------------------
# IDANTIFIKASYON (etap 1) AK PWENTAJ (etap 2)
# ---------------------------------------------------------------------------

def _record_failure(db: Session, request: Request, device: KioskDevice,
                    emp: Optional[Employee], now: datetime) -> None:
    device.failed_count = (device.failed_count or 0) + 1
    device_locked = device.failed_count >= MAX_DEVICE_FAILURES
    if device_locked:
        device.locked_until = now + DEVICE_LOCK
        device.failed_count = 0

    emp_locked = False
    if emp is not None:
        emp.kiosk_failed_count = (emp.kiosk_failed_count or 0) + 1
        emp_locked = emp.kiosk_failed_count >= MAX_PIN_FAILURES
        if emp_locked:
            emp.kiosk_locked_until = now + PIN_LOCK
            emp.kiosk_failed_count = 0
    db.commit()

    if device_locked:
        _audit(db, request, device.organization_id, None, "kiosk_device_lock",
               "kiosk_device", device.id, f"{MAX_DEVICE_FAILURES} move esè.")
    if emp_locked:
        _audit(db, request, device.organization_id, None, "kiosk_pin_lock",
               "employee", emp.id, f"{MAX_PIN_FAILURES} move kòd sou tablèt {device.name}.")


def _authenticate(db: Session, request: Request, device: KioskDevice,
                  number: Optional[str], pin: str, now: datetime) -> Employee:
    """Menm verifikasyon pou /identify ak /punch. Voye HTTPException si l pa bon."""
    org_id = device.organization_id
    device.last_seen_at = now

    if get_clock_mode(db, org_id) == PHONE:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Biznis la pa sèvi ak tablèt pou pwentaj.")

    if device.locked_until and _as_aware(device.locked_until) > now:
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Twòp move esè sou tablèt sa a. Tann kèk minit.")

    pin_mode = get_pin_mode(db, org_id)
    if number and number.strip():
        emp = _find_employee(db, org_id, number)       # nimewo toujou aksepte
    elif pin_mode == PIN_ONLY:
        emp = _find_by_pin(db, org_id, pin)
    else:
        emp = None

    if emp is not None and emp.kiosk_locked_until and _as_aware(emp.kiosk_locked_until) > now:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Twòp move kòd. Tann kèk minit, oswa mande manadjè w yon nouvo kòd.",
        )

    if emp is None or not verify_pin(pin, emp.kiosk_pin_hash):
        _record_failure(db, request, device, emp, now)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CREDENTIALS)

    emp.kiosk_failed_count = 0
    emp.kiosk_locked_until = None
    device.failed_count = 0
    device.locked_until = None

    # Ansyen kòd (anvan mòd "kòd sèlman"): li jwenn kle rechèch li kounye a,
    # sèlman si pèsonn lòt nan biznis la pa gen menm kòd la.
    if not emp.kiosk_pin_lookup:
        lookup = pin_lookup(org_id, pin)
        if not _lookup_taken(db, org_id, lookup, emp.id):
            emp.kiosk_pin_lookup = lookup

    if emp.status != EmploymentStatus.ACTIVE:
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Ou pa ka klòk in: estati w se pa aktif.")
    return emp


class IdentifyRequest(BaseModel):
    employee_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    pin: str = Field(min_length=4, max_length=12)


class IdentifyResult(BaseModel):
    first_name: str                 # prenon sèlman: tablèt la nan yon kote piblik
    photo_url: Optional[str] = None
    clocked_in: bool
    since: Optional[datetime] = None
    elapsed_minutes: Optional[int] = None


@router.post("/identify", response_model=IdentifyResult)
def identify(payload: IdentifyRequest, device: KioskDeviceDep, request: Request, db: DbSession):
    """Etap 1: kiyès sa ye, e èske l antre deja? Pa anrejistre okenn pwentaj."""
    now = _now()
    emp = _authenticate(db, request, device, payload.employee_number, payload.pin, now)
    open_entry = _open_entry_for(db, device.organization_id, emp.id)
    db.commit()
    since = _as_aware(open_entry.clock_in_at) if open_entry else None
    return IdentifyResult(
        first_name=emp.first_name, photo_url=photo_url_for(db, emp.id),
        clocked_in=open_entry is not None, since=since,
        elapsed_minutes=int((now - since).total_seconds() // 60) if since else None,
    )


class PunchRequest(BaseModel):
    employee_number: Optional[str] = Field(default=None, min_length=1, max_length=50)
    pin: str = Field(min_length=4, max_length=12)
    action: Literal["in", "out"]
    break_minutes: int = Field(default=0, ge=0, le=240)


class PunchResult(BaseModel):
    action: Literal["in", "out"]
    first_name: str                 # prenon sèlman: tablèt la nan yon kote piblik
    at: datetime
    worked_minutes: Optional[int] = None
    photo_url: Optional[str] = None


@router.post("/punch", response_model=PunchResult)
def punch(payload: PunchRequest, device: KioskDeviceDep, request: Request, db: DbSession):
    org_id = device.organization_id
    now = _now()
    emp = _authenticate(db, request, device, payload.employee_number, payload.pin, now)
    photo = photo_url_for(db, emp.id)

    open_entry = _open_entry_for(db, org_id, emp.id)

    # --- ANTRE ---
    if payload.action == "in":
        if open_entry is not None:
            db.commit()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Ou deja antre. Fè sòti anvan.")
        tz = _org_tz(db, org_id)
        db.add(TimeEntry(
            organization_id=org_id,
            employee_id=emp.id,
            work_date=now.astimezone(tz).date(),     # jou LOKAL, pa jou UTC
            clock_in_at=now,
            status=AttendanceStatus.OPEN,
            clock_in_ip=request.client.host if request.client else None,
            device_info=f"kiosk:{device.id} {device.name}"[:255],
        ))
        db.commit()
        return PunchResult(action="in", first_name=emp.first_name, at=now, photo_url=photo)

    # --- SÒTI ---
    if open_entry is None:
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Ou pa antre. Fè antre anvan.")

    raw_minutes = int((now - _as_aware(open_entry.clock_in_at)).total_seconds() // 60)
    if raw_minutes > MAX_SHIFT_MINUTES:
        # Moun nan bliye sòti: menm règ ak attendance.py.
        open_entry.clock_out_at = now
        open_entry.break_minutes = payload.break_minutes
        open_entry.worked_minutes = 0
        open_entry.overtime_minutes = 0
        open_entry.status = AttendanceStatus.MISSING_OUT
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Jounen an gen plis pase {MAX_SHIFT_MINUTES // 60} èdtan. "
                "Nou make l pou HR korije l."
            ),
        )

    open_entry.clock_out_at = now
    open_entry.break_minutes = payload.break_minutes
    worked, overtime = _compute_minutes(open_entry)
    open_entry.worked_minutes = worked
    open_entry.overtime_minutes = overtime
    open_entry.status = AttendanceStatus.CLOSED
    db.commit()
    return PunchResult(action="out", first_name=emp.first_name, at=now,
                       worked_minutes=worked, photo_url=photo)