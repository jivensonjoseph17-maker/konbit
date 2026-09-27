"""
Konbit — Router Ekip (paj manadjè a)
Chemen: backend/app/routers/team.py

    GET /api/team/today         Ekip mwen jodi a: kiyès ki antre, an reta, absan, an konje
    GET /api/team/inbox-count   Konbyen bagay k ap tann mwen (konje + èdtan) — pou ti chif meni an

KIYÈS NOU MONTRE:
  - Manadjè: moun ki rapòte dirèkteman ba li (menm règ ak /attendance/today).
  - HR / admin: tout anplwaye aktif biznis la.
  - Pèsonn pa wè pwòp liy pa l isit la.

ESTATI (an lè LOKAL biznis la):
  working      li antre, li poko soti
  done         li antre epi li soti
  missing_out  jounen an make "san klòk out" (HR dwe korije)
  on_leave     yon konje APWOUVE kouvri jodi a
  absent       li gen yon orè pibliye jodi a, lè a pase (+10 min), li poko antre
  not_yet      li gen yon orè jodi a ki poko kòmanse
  off          li gen orè semèn nan men pa jodi a, oswa se wikenn
  no_record    pa gen orè, pa gen pwentaj (jou semèn)
`late` = li antre plis pase 10 min apre kòmansman orè l (oswa apre LATE_AFTER si pa gen orè).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId
from ..models import (
    AttendanceStatus,
    Employee,
    LeaveRequest,
    LeaveType,
    PayPeriod,
    PayrollStatus,
    RequestStatus,
    Shift,
    TimeEntry,
    User,
    UserRole,
)
from ..timezone_utils import get_local_today, get_org_timezone
from .attendance import LATE_AFTER
from .leaves import pending_for_me
from .timesheets import period_timesheets

router = APIRouter()

HR_ROLES = (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
LATE_GRACE = timedelta(minutes=10)
STATUSES = ("working", "done", "missing_out", "on_leave", "absent", "not_yet", "off", "no_record")


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _team(db: Session, user: User, org_id: int) -> list[Employee]:
    q = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
    )
    if user.role in HR_ROLES:
        pass
    elif user.role == UserRole.MANAGER:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        q = q.filter(Employee.manager_id == viewer.id)
    else:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou paj sa a.")

    q = q.filter(or_(Employee.user_id.is_(None), Employee.user_id != user.id))
    return q.order_by(Employee.first_name, Employee.last_name).all()


# ---------------------------------------------------------------------------
# EKIP MWEN JODI A
# ---------------------------------------------------------------------------

class TeamMember(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    status: str
    late: bool = False
    clock_in_at: Optional[datetime] = None
    clock_out_at: Optional[datetime] = None
    worked_minutes: Optional[int] = None
    shift_start: Optional[str] = None       # "08:00" — lè LOKAL
    shift_end: Optional[str] = None
    leave_type: Optional[LeaveType] = None


class TeamToday(BaseModel):
    work_date: date
    counts: dict[str, int]                  # pa estati
    late_count: int
    total: int
    items: list[TeamMember]


@router.get("/today", response_model=TeamToday)
def team_today(user: CurrentUser, org_id: TenantId, db: DbSession):
    team = _team(db, user, org_id)
    today = get_local_today(db, org_id)
    tz = get_org_timezone(db, org_id)
    now = datetime.now(timezone.utc)
    now_local = now.astimezone(tz)
    ids = [e.id for e in team]

    entries: dict[int, TimeEntry] = {}
    leaves: dict[int, LeaveRequest] = {}
    shifts_today: dict[int, Shift] = {}
    has_week_shift: set[int] = set()

    if ids:
        # Dènye pwentaj jodi a pou chak moun
        for e in db.query(TimeEntry).filter(
            TimeEntry.organization_id == org_id,
            TimeEntry.employee_id.in_(ids),
            TimeEntry.work_date == today,
        ).order_by(TimeEntry.clock_in_at).all():
            entries[e.employee_id] = e

        for lv in db.query(LeaveRequest).filter(
            LeaveRequest.organization_id == org_id,
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status == RequestStatus.APPROVED,
            LeaveRequest.start_date <= today,
            LeaveRequest.end_date >= today,
        ).all():
            leaves[lv.employee_id] = lv

        # Sèlman orè PIBLIYE yo: yon bouyon pa vle di anyen pou anplwaye a.
        week_start = today - timedelta(days=today.weekday())
        for s in db.query(Shift).filter(
            Shift.organization_id == org_id,
            Shift.employee_id.in_(ids),
            Shift.is_published.is_(True),
            Shift.work_date >= week_start,
            Shift.work_date <= week_start + timedelta(days=6),
        ).all():
            has_week_shift.add(s.employee_id)
            if s.work_date == today:
                shifts_today[s.employee_id] = s

    items: list[TeamMember] = []
    for emp in team:
        e = entries.get(emp.id)
        s = shifts_today.get(emp.id)
        lv = leaves.get(emp.id)
        shift_start = datetime.combine(today, s.start_time, tzinfo=tz) if s else None
        late = False
        worked = None

        if e is not None:
            if e.status == AttendanceStatus.OPEN:
                status = "working"
                worked = max(0, int((now - _as_aware(e.clock_in_at)).total_seconds() // 60))
            elif e.status == AttendanceStatus.MISSING_OUT:
                status = "missing_out"
            else:
                status = "done"
                worked = e.worked_minutes
            clock_in_local = _as_aware(e.clock_in_at).astimezone(tz)
            late = (clock_in_local > shift_start + LATE_GRACE) if shift_start \
                else clock_in_local.time() > LATE_AFTER
        elif lv is not None:
            status = "on_leave"
        elif shift_start is not None:
            status = "absent" if now_local > shift_start + LATE_GRACE else "not_yet"
        elif emp.id in has_week_shift or today.weekday() >= 5:
            status = "off"
        else:
            status = "no_record"

        items.append(TeamMember(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
            status=status,
            late=late,
            clock_in_at=e.clock_in_at if e else None,
            clock_out_at=e.clock_out_at if e else None,
            worked_minutes=worked,
            shift_start=s.start_time.strftime("%H:%M") if s else None,
            shift_end=s.end_time.strftime("%H:%M") if s else None,
            leave_type=lv.leave_type if lv else None,
        ))

    counts = {st: 0 for st in STATUSES}
    for it in items:
        counts[it.status] += 1

    return TeamToday(
        work_date=today,
        counts=counts,
        late_count=sum(1 for it in items if it.late),
        total=len(items),
        items=items,
    )


# ---------------------------------------------------------------------------
# KONBYEN BAGAY K AP TANN MWEN
# ---------------------------------------------------------------------------

class InboxCount(BaseModel):
    leaves: int = 0
    timesheets: int = 0
    total: int = 0
    period_id: Optional[int] = None         # dènye peryòd ki fini, pewòl poko apwouve
    period_name: Optional[str] = None


@router.get("/inbox-count", response_model=InboxCount)
def inbox_count(user: CurrentUser, org_id: TenantId, db: DbSession):
    """
    Pou ti chif wouj bò kote "Ekip mwen" nan meni an. Yon anplwaye senp
    resevwa 0 (pa yon erè): meni an rele sa pou tout moun ki wè lyen an.
    """
    if user.role not in HR_ROLES and user.role != UserRole.MANAGER:
        return InboxCount()

    try:
        leaves = pending_for_me(user=user, org_id=org_id, db=db).total
    except HTTPException:
        leaves = 0

    result = InboxCount(leaves=leaves)

    # Èdtan: dènye peryòd ki FINI men pewòl li poko apwouve.
    today = get_local_today(db, org_id)
    period = db.query(PayPeriod).filter(
        PayPeriod.organization_id == org_id,
        PayPeriod.end_date < today,
        PayPeriod.status == PayrollStatus.DRAFT,
    ).order_by(PayPeriod.end_date.desc()).first()
    if period is not None:
        try:
            data = period_timesheets(period_id=period.id, user=user, org_id=org_id, db=db)
            result.timesheets = sum(
                1 for r in data.items
                if r.can_decide and r.status == "pending" and r.days_present > 0
            )
            result.period_id = period.id
            result.period_name = period.name
        except HTTPException:
            pass

    result.total = result.leaves + result.timesheets
    return result