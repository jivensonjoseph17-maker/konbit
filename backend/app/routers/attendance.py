"""
Konbit — Router Prezans (Clock in / Clock out)
Chemen: backend/app/routers/attendance.py

Endpoint yo:
    GET    /api/attendance/status              Èske m klòk in kounye a?
    POST   /api/attendance/clock-in            Kòmanse jounen an
    POST   /api/attendance/clock-out           Fini jounen an
    GET    /api/attendance/me                  Pwòp istorik mwen
    GET    /api/attendance/me/summary          Rezime pa peryòd
    GET    /api/attendance/today               Kiyès ki la jodi a (manadjè/HR)
    GET    /api/attendance/employee/{id}       Istorik yon anplwaye
    GET    /api/attendance/employee/{id}/summary
    PATCH  /api/attendance/{entry_id}          Koreksyon HR (rezon obligatwa)
    POST   /api/attendance/close-open-entries  Fèmen jounen moun ki bliye (HR)

DESIZYON: nou pa efase yon antre ki gen erè. HR korije l epi antre a pran
estati ADJUSTED, ak rezon an ekri. Se konsa yon kontab ka verifye pewòl la.

BLOKAJ: lè yon manadjè apwouve èdtan yon moun pou yon peryòd (gade
timesheets.py), pwentaj peryòd sa a BLOKE. HR dwe retire apwobasyon an
anvan li korije yon lè — sinon èdtan yo ta ka chanje apre siyati a.
"""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    require_hr,
)
from ..models import (
    AttendanceStatus,
    AuditLog,
    Employee,
    EmploymentStatus,
    TimeEntry,
    User,
    UserRole,
)
from ..schemas import (
    AttendanceSummary,
    ClockInRequest,
    ClockOutRequest,
    Message,
    TimeEntryAdjust,
    TimeEntryOut,
)
from ..timezone_utils import get_local_today, get_org_timezone
from .timesheets import timesheet_locked

logger = logging.getLogger("konbit")

router = APIRouter()

STANDARD_WORKDAY_MINUTES = 8 * 60      # 8 èdtan — apre sa se èdtan siplemantè
MAX_SHIFT_MINUTES = 16 * 60            # gad kont move done


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _audit(db: Session, request: Request, user: User, action: str,
           entity_id: int, changes: Optional[str] = None) -> None:
    try:
        db.add(AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action=action,
            entity_type="time_entry",
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


LATE_AFTER = time(9, 0)          # lè lokal apre sa yon moun konte an reta

# Fizo orè biznis la: TOUT kalkil dat (ki jou yon moun travay, kiyès ki la
# jodi a, kiyès ki an reta) fèt nan lè LOKAL biznis la, pa an UTC. Lojik la
# nan timezone_utils.py, pataje ak leaves.py, training.py ak applications.py.
_org_tz = get_org_timezone
_local_today = get_local_today


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    SQLite retounen datetime san fizo orè. Si nou soustrè yon datetime
    'naive' ak yon 'aware', Python voye TypeError. Nou nòmalize tout bagay.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _compute_minutes(entry: TimeEntry) -> tuple[int, int]:
    """Retounen (minit travay, minit siplemantè)."""
    clock_in = _as_aware(entry.clock_in_at)
    clock_out = _as_aware(entry.clock_out_at)
    if clock_in is None or clock_out is None:
        return 0, 0

    total = int((clock_out - clock_in).total_seconds() // 60)
    total -= (entry.break_minutes or 0)
    total = max(0, total)

    overtime = max(0, total - STANDARD_WORKDAY_MINUTES)
    return total, overtime


def _open_entry_for(db: Session, org_id: int, employee_id: int) -> Optional[TimeEntry]:
    return db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
        TimeEntry.status == AttendanceStatus.OPEN,
    ).order_by(TimeEntry.clock_in_at.desc()).first()


def _get_employee_or_404(db: Session, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    return emp


# ---------------------------------------------------------------------------
# ESTATI
# ---------------------------------------------------------------------------

class ClockStatus(BaseModel):
    clocked_in: bool
    entry: Optional[TimeEntryOut] = None
    elapsed_minutes: Optional[int] = None
    message: str


@router.get("/status", response_model=ClockStatus)
def my_clock_status(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """Frontend lan rele sa a pou l konnen ki bouton pou l montre."""
    entry = _open_entry_for(db, org_id, emp.id)
    if entry is None:
        return ClockStatus(clocked_in=False, message="Ou pa klòk in.")

    elapsed = int((_now() - _as_aware(entry.clock_in_at)).total_seconds() // 60)
    return ClockStatus(
        clocked_in=True,
        entry=TimeEntryOut.model_validate(entry),
        elapsed_minutes=elapsed,
        message=f"Ou klòk in depi {elapsed // 60}è {elapsed % 60}min.",
    )


# ---------------------------------------------------------------------------
# CLOCK IN
# ---------------------------------------------------------------------------

@router.post("/clock-in", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def clock_in(
    payload: ClockInRequest,
    emp: CurrentEmployee,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Kòmanse jounen travay la.
    Nou anpeche yon dezyèm clock in si gen youn ki louvri — sinon
    ou t ap gen de jounen an menm tan epi pewòl la ap konte de fwa.
    """
    if emp.status != EmploymentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ou pa ka klòk in: estati w se pa aktif.",
        )

    existing = _open_entry_for(db, org_id, emp.id)
    if existing is not None:
        elapsed = int((_now() - _as_aware(existing.clock_in_at)).total_seconds() // 60)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ou deja klòk in depi {elapsed // 60}è {elapsed % 60}min. "
                "Fè klòk out anvan."
            ),
        )

    now = _now()
    tz = _org_tz(db, org_id)
    entry = TimeEntry(
        organization_id=org_id,
        employee_id=emp.id,
        work_date=now.astimezone(tz).date(),     # jou LOKAL, pa jou UTC
        clock_in_at=now,
        status=AttendanceStatus.OPEN,
        clock_in_lat=payload.latitude,
        clock_in_lng=payload.longitude,
        clock_in_ip=request.client.host if request.client else None,
        device_info=(payload.device_info or request.headers.get("user-agent", ""))[:255],
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# CLOCK OUT
# ---------------------------------------------------------------------------

@router.post("/clock-out", response_model=TimeEntryOut)
def clock_out(
    payload: ClockOutRequest,
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
):
    entry = _open_entry_for(db, org_id, emp.id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ou pa gen okenn jounen ki louvri. Fè klòk in anvan.",
        )

    now = _now()
    clock_in_at = _as_aware(entry.clock_in_at)
    raw_minutes = int((now - clock_in_at).total_seconds() // 60)

    if raw_minutes > MAX_SHIFT_MINUTES:
        # Moun nan bliye klòk out. Nou make l pou HR korije.
        entry.clock_out_at = now
        entry.break_minutes = payload.break_minutes
        entry.worked_minutes = 0
        entry.overtime_minutes = 0
        entry.status = AttendanceStatus.MISSING_OUT
        db.commit()
        db.refresh(entry)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Jounen an gen plis pase {MAX_SHIFT_MINUTES // 60} èdtan. "
                "Nou make l pou HR korije l."
            ),
        )

    entry.clock_out_at = now
    entry.break_minutes = payload.break_minutes
    entry.clock_out_lat = payload.latitude
    entry.clock_out_lng = payload.longitude

    worked, overtime = _compute_minutes(entry)
    entry.worked_minutes = worked
    entry.overtime_minutes = overtime
    entry.status = AttendanceStatus.CLOSED

    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# ISTORIK
# ---------------------------------------------------------------------------

class TimeEntryList(BaseModel):
    total: int
    items: list[TimeEntryOut]


def _entries_query(db: Session, org_id: int, employee_id: int,
                   start: Optional[date], end: Optional[date]):
    q = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
    )
    if start:
        q = q.filter(TimeEntry.work_date >= start)
    if end:
        q = q.filter(TimeEntry.work_date <= end)
    return q


@router.get("/me", response_model=TimeEntryList)
def my_entries(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
):
    q = _entries_query(db, org_id, emp.id, start_date, end_date)
    total = q.count()
    items = q.order_by(TimeEntry.work_date.desc(), TimeEntry.clock_in_at.desc()).limit(limit).all()
    return TimeEntryList(total=total, items=[TimeEntryOut.model_validate(e) for e in items])


@router.get("/employee/{employee_id}", response_model=TimeEntryList)
def employee_entries(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
):
    target = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, target, db)

    q = _entries_query(db, org_id, employee_id, start_date, end_date)
    total = q.count()
    items = q.order_by(TimeEntry.work_date.desc()).limit(limit).all()
    return TimeEntryList(total=total, items=[TimeEntryOut.model_validate(e) for e in items])


# ---------------------------------------------------------------------------
# REZIME
# ---------------------------------------------------------------------------

def _build_summary(db: Session, org_id: int, employee_id: int,
                   start: date, end: date) -> AttendanceSummary:
    tz = _org_tz(db, org_id)
    rows = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
        TimeEntry.work_date >= start,
        TimeEntry.work_date <= end,
    ).all()

    worked_days = {r.work_date for r in rows}
    total_worked = sum(r.worked_minutes or 0 for r in rows)
    total_overtime = sum(r.overtime_minutes or 0 for r in rows)

    # Jou travay yo nan peryòd la (lendi jiska vandredi)
    business_days = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            business_days += 1
        cursor += timedelta(days=1)

    # Moun ki rive apre 9:00, an lè LOKAL biznis la
    late = 0
    for r in rows:
        ci = _as_aware(r.clock_in_at)
        if ci and ci.astimezone(tz).time() > LATE_AFTER:
            late += 1

    return AttendanceSummary(
        employee_id=employee_id,
        period_start=start,
        period_end=end,
        days_present=len(worked_days),
        days_absent=max(0, business_days - len(worked_days)),
        total_worked_minutes=total_worked,
        total_overtime_minutes=total_overtime,
        late_arrivals=late,
    )


@router.get("/me/summary", response_model=AttendanceSummary)
def my_summary(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    end = end_date or _local_today(db, org_id)
    start = start_date or end.replace(day=1)
    return _build_summary(db, org_id, emp.id, start, end)


@router.get("/employee/{employee_id}/summary", response_model=AttendanceSummary)
def employee_summary(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    target = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, target, db)
    end = end_date or _local_today(db, org_id)
    start = start_date or end.replace(day=1)
    return _build_summary(db, org_id, employee_id, start, end)


# ---------------------------------------------------------------------------
# KIYÈS KI LA JODI A
# ---------------------------------------------------------------------------

class PresentToday(BaseModel):
    employee_id: int
    full_name: str
    employee_number: str
    clock_in_at: datetime
    clocked_out: bool
    worked_minutes: Optional[int] = None


class TodayBoard(BaseModel):
    work_date: date
    present_count: int
    still_working: int
    total_active_employees: int
    present: list[PresentToday]


@router.get("/today", response_model=TodayBoard)
def today_board(user: CurrentUser, org_id: TenantId, db: DbSession):
    """
    Tablo prezans jodi a. HR ak admin wè tout moun;
    yon manadjè wè sèlman ekip dirèk li.
    """
    today = _local_today(db, org_id)

    q = (
        db.query(TimeEntry, Employee)
        .join(Employee, TimeEntry.employee_id == Employee.id)
        .filter(
            TimeEntry.organization_id == org_id,
            TimeEntry.work_date == today,
        )
    )

    if user.role == UserRole.MANAGER:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        q = q.filter(Employee.manager_id == viewer.id)

    rows = q.order_by(TimeEntry.clock_in_at).all()

    present = [
        PresentToday(
            employee_id=emp.id,
            full_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
            clock_in_at=entry.clock_in_at,
            clocked_out=entry.status != AttendanceStatus.OPEN,
            worked_minutes=entry.worked_minutes,
        )
        for entry, emp in rows
    ]

    total_active = db.query(func.count(Employee.id)).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.status == EmploymentStatus.ACTIVE,
    ).scalar() or 0

    return TodayBoard(
        work_date=today,
        present_count=len({p.employee_id for p in present}),
        still_working=sum(1 for p in present if not p.clocked_out),
        total_active_employees=total_active,
        present=present,
    )


# ---------------------------------------------------------------------------
# KOREKSYON HR
# ---------------------------------------------------------------------------

@router.patch(
    "/{entry_id}",
    response_model=TimeEntryOut,
    dependencies=[Depends(require_hr)],
)
def adjust_entry(
    entry_id: int,
    payload: TimeEntryAdjust,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Korije yon antre. `reason` obligatwa epi li ale nan jounal odit la.
    Nou pa efase done a — nou make l ADJUSTED.
    """
    entry = db.query(TimeEntry).filter(
        TimeEntry.id == entry_id,
        TimeEntry.organization_id == org_id,
    ).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="Antre a pa jwenn.")

    if timesheet_locked(db, org_id, entry.employee_id, entry.work_date):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Manadjè a deja apwouve èdtan peryòd sa a. Retire apwobasyon an "
                "anvan ou korije l — manadjè a ap dwe apwouve ankò."
            ),
        )

    before = (
        f"in={entry.clock_in_at}, out={entry.clock_out_at}, "
        f"break={entry.break_minutes}, worked={entry.worked_minutes}"
    )

    if payload.clock_in_at is not None:
        entry.clock_in_at = payload.clock_in_at
    if payload.clock_out_at is not None:
        entry.clock_out_at = payload.clock_out_at
    if payload.break_minutes is not None:
        entry.break_minutes = payload.break_minutes

    ci = _as_aware(entry.clock_in_at)
    co = _as_aware(entry.clock_out_at)
    if ci and co and co <= ci:
        raise HTTPException(
            status_code=400,
            detail="Klòk out la pa ka anvan oswa egal ak klòk in lan.",
        )

    worked, overtime = _compute_minutes(entry)
    entry.worked_minutes = worked
    entry.overtime_minutes = overtime
    entry.status = AttendanceStatus.ADJUSTED if co else AttendanceStatus.OPEN
    entry.adjusted_by_id = user.id
    entry.adjustment_reason = payload.reason

    db.commit()
    db.refresh(entry)
    _audit(db, request, user, "adjust", entry.id,
           changes=f"{before} -> in={entry.clock_in_at}, out={entry.clock_out_at}. "
                   f"Rezon: {payload.reason}")
    return entry


# ---------------------------------------------------------------------------
# FÈMEN JOUNEN MOUN KI BLIYE
# ---------------------------------------------------------------------------

class CloseOpenResult(BaseModel):
    closed_count: int
    entry_ids: list[int]
    note: str


@router.post(
    "/close-open-entries",
    response_model=CloseOpenResult,
    dependencies=[Depends(require_hr)],
)
def close_open_entries(
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
    older_than_hours: Annotated[int, Query(ge=8, le=72)] = 16,
):
    """
    Fèmen tout jounen ki rete louvri twò lontan epi make yo MISSING_OUT.
    San sa, antre sa yo ap bloke anplwaye a pou l pa ka klòk in demen.
    Ideyalman yon travay otomatik rele sa chak swa.
    """
    cutoff = _now() - timedelta(hours=older_than_hours)

    entries = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.status == AttendanceStatus.OPEN,
        TimeEntry.clock_in_at < cutoff,
    ).all()

    ids = []
    for entry in entries:
        entry.status = AttendanceStatus.MISSING_OUT
        entry.worked_minutes = 0
        entry.overtime_minutes = 0
        entry.adjustment_reason = (
            f"Fèmen otomatikman: pa gen klòk out apre {older_than_hours} èdtan."
        )
        entry.adjusted_by_id = user.id
        ids.append(entry.id)

    db.commit()
    for entry_id in ids:
        _audit(db, request, user, "auto_close", entry_id)

    return CloseOpenResult(
        closed_count=len(ids),
        entry_ids=ids,
        note=(
            "Antre sa yo make MISSING_OUT ak 0 minit. HR dwe korije chak youn "
            "ak vrè lè a anvan pewòl la kalkile."
        ),
    )