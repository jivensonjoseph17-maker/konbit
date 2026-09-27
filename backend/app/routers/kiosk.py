"""
Konbit — Router Kiyòsk (pwentaj sou tablèt biznis la ak kòd pèsonèl)
Chemen: backend/app/routers/kiosk.py

Administrasyon (kont konekte):
    GET    /api/kiosk/settings                 Mòd pwentaj biznis la (tout anplwaye)
    PUT    /api/kiosk/settings                 Chanje mòd la (admin)
    GET    /api/kiosk/devices                  Tablèt yo (admin)
    POST   /api/kiosk/devices                  Aktive yon tablèt → token (yon sèl fwa)
    DELETE /api/kiosk/devices/{id}             Dezaktive yon tablèt (admin)
    POST   /api/kiosk/employees/{id}/pin       Bay / rejenere kòd yon anplwaye

Tablèt la (header X-Kiosk-Token, PA token itilizatè):
    GET    /api/kiosk/device                   Non tablèt la ak biznis la
    POST   /api/kiosk/punch                    Antre / sòti ak nimewo + kòd

SEKIRITE:
  - Token tablèt la ak kòd yo pa janm estoke an klè (sha256 / PBKDF2).
    Kòd la parèt YON SÈL FWA, lè admin/manadjè a jenere l.
  - Token tablèt la pa ka fè anyen lòt pase pwentaj: se pa yon kont itilizatè.
  - 5 move kòd pou yon anplwaye → kòd li bloke 15 minit.
    20 move esè sou yon tablèt → tablèt la bloke 10 minit.
  - Menm mesaj erè pou "nimewo sa a pa egziste" ak "move kòd".
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
from sqlalchemy.orm import Session

from ..clock_mode import PHONE, get_clock_mode
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
    Organization,
    TimeEntry,
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

router = APIRouter()

HR_ROLES = (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)

PIN_LENGTH = 6
MAX_PIN_FAILURES = 5
PIN_LOCK = timedelta(minutes=15)
MAX_DEVICE_FAILURES = 20
DEVICE_LOCK = timedelta(minutes=10)
_PBKDF2_ITERATIONS = 120_000

_WEAK_PINS = {d * PIN_LENGTH for d in "0123456789"} | {
    "123456", "654321", "012345", "123123", "121212", "112233",
}

NOT_ACTIVATED = "Tablèt sa a pa aktive."
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


def _new_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"
        if pin not in _WEAK_PINS:
            return pin


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
# MÒD PWENTAJ
# ---------------------------------------------------------------------------

class ClockSettings(BaseModel):
    clock_mode: Literal["phone", "kiosk", "both"]


@router.get("/settings", response_model=ClockSettings)
def read_settings(org_id: TenantId, db: DbSession):
    """Tout anplwaye ka li l: tablo de bò a kache bouton Klòk in lan si mòd la se 'kiosk'."""
    return ClockSettings(clock_mode=get_clock_mode(db, org_id))


@router.put("/settings", response_model=ClockSettings, dependencies=[Depends(require_admin)])
def update_settings(payload: ClockSettings, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    org = db.get(Organization, org_id)
    before = get_clock_mode(db, org_id)
    org.clock_mode = payload.clock_mode
    db.commit()
    _audit(db, request, org_id, user.id, "update", "organization", org_id,
           f"clock_mode: {before} -> {payload.clock_mode}")
    return payload


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

    pin = _new_pin()
    now = datetime.now(timezone.utc)
    target.kiosk_pin_hash = hash_pin(pin)
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
# PWENTAJ SOU TABLÈT LA
# ---------------------------------------------------------------------------

class DeviceInfo(BaseModel):
    device_name: str
    organization_name: str
    clock_mode: str


@router.get("/device", response_model=DeviceInfo)
def device_info(device: KioskDeviceDep, db: DbSession):
    org = db.get(Organization, device.organization_id)
    device.last_seen_at = _now()
    db.commit()
    return DeviceInfo(device_name=device.name, organization_name=org.name,
                      clock_mode=get_clock_mode(db, device.organization_id))


class PunchRequest(BaseModel):
    employee_number: str = Field(min_length=1, max_length=50)
    pin: str = Field(min_length=4, max_length=12)
    action: Literal["in", "out"]
    break_minutes: int = Field(default=0, ge=0, le=240)


class PunchResult(BaseModel):
    action: Literal["in", "out"]
    first_name: str                 # prenon sèlman: tablèt la nan yon kote piblik
    at: datetime
    worked_minutes: Optional[int] = None


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


@router.post("/punch", response_model=PunchResult)
def punch(payload: PunchRequest, device: KioskDeviceDep, request: Request, db: DbSession):
    org_id = device.organization_id
    now = _now()
    device.last_seen_at = now

    if get_clock_mode(db, org_id) == PHONE:
        db.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Biznis la pa sèvi ak tablèt pou pwentaj.")

    if device.locked_until and _as_aware(device.locked_until) > now:
        db.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Twòp move esè sou tablèt sa a. Tann kèk minit.")

    emp = _find_employee(db, org_id, payload.employee_number)

    if emp is not None and emp.kiosk_locked_until and _as_aware(emp.kiosk_locked_until) > now:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Twòp move kòd. Tann kèk minit, oswa mande manadjè w yon nouvo kòd.",
        )

    if emp is None or not verify_pin(payload.pin, emp.kiosk_pin_hash):
        _record_failure(db, request, device, emp, now)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=BAD_CREDENTIALS)

    emp.kiosk_failed_count = 0
    emp.kiosk_locked_until = None
    device.failed_count = 0
    device.locked_until = None

    if emp.status != EmploymentStatus.ACTIVE:
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Ou pa ka klòk in: estati w se pa aktif.")

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
        return PunchResult(action="in", first_name=emp.first_name, at=now)

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
    return PunchResult(action="out", first_name=emp.first_name, at=now, worked_minutes=worked)