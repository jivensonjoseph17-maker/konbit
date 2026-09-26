"""
Konbit — Router Apwobasyon Tan Travay
Chemen: backend/app/routers/timesheets.py

    GET    /api/timesheets/periods                              Peryòd yo (manadjè + HR)
    GET    /api/timesheets/{period_id}                          Fèy tan ekip mwen pou peryòd la
    POST   /api/timesheets/{period_id}/employees/{emp_id}/approve   Apwouve èdtan yon moun
    POST   /api/timesheets/{period_id}/employees/{emp_id}/return    Voye l bay HR (nòt obligatwa)
    DELETE /api/timesheets/{period_id}/employees/{emp_id}           HR retire apwobasyon an

RÈG YO (manadjè a prepare, HR/admin peye):
  - Manadjè a apwouve èdtan moun ki anba l. HR/admin ka apwouve pou tout moun.
  - PÈSONN pa apwouve pwòp èdtan pa l.
  - Nou apwouve sèlman yon peryòd ki FINI, e san pwentaj ki toujou louvri.
  - Yon apwobasyon BLOKE pwentaj yo: HR dwe retire l anvan li korije yon lè.
  - Pewòl la peye èdtan siplemantè SÈLMAN pou moun ki gen èdtan apwouve.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, is_in_management_chain, require_hr
from ..models import (
    AttendanceStatus,
    AuditLog,
    Employee,
    Notification,
    PayPeriod,
    PayrollStatus,
    TimeEntry,
    TimesheetApproval,
    TimesheetStatus,
    User,
    UserRole,
)
from ..timezone_utils import get_local_today

logger = logging.getLogger("konbit")

router = APIRouter()

HR_ROLES = (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR)
PROBLEM_STATUSES = (AttendanceStatus.OPEN, AttendanceStatus.MISSING_OUT)
COUNTED_STATUSES = (AttendanceStatus.CLOSED, AttendanceStatus.ADJUSTED)


# ---------------------------------------------------------------------------
# ZOUTI PATAJE (attendance.py ak payroll.py sèvi ak yo tou)
# ---------------------------------------------------------------------------

def timesheet_locked(db: Session, org_id: int, employee_id: int, work_date: date) -> bool:
    """Èske yon apwobasyon kouvri jou sa a pou moun sa a? Si wi, pèsonn pa manyen l."""
    return db.query(TimesheetApproval.id).join(
        PayPeriod, TimesheetApproval.pay_period_id == PayPeriod.id,
    ).filter(
        TimesheetApproval.organization_id == org_id,
        TimesheetApproval.employee_id == employee_id,
        TimesheetApproval.status == TimesheetStatus.APPROVED,
        PayPeriod.start_date <= work_date,
        PayPeriod.end_date >= work_date,
    ).first() is not None


def approved_employee_ids(db: Session, org_id: int, period_id: int) -> set[int]:
    rows = db.query(TimesheetApproval.employee_id).filter(
        TimesheetApproval.organization_id == org_id,
        TimesheetApproval.pay_period_id == period_id,
        TimesheetApproval.status == TimesheetStatus.APPROVED,
    ).all()
    return {r[0] for r in rows}


def has_time_entries(db: Session, org_id: int, employee_id: int, start: date, end: date) -> bool:
    return db.query(TimeEntry.id).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
        TimeEntry.work_date >= start,
        TimeEntry.work_date <= end,
    ).first() is not None


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
            entity_type="timesheet",
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _get_period_or_404(db: Session, org_id: int, period_id: int) -> PayPeriod:
    period = db.query(PayPeriod).filter(
        PayPeriod.id == period_id,
        PayPeriod.organization_id == org_id,
    ).first()
    if period is None:
        raise HTTPException(status_code=404, detail="Peryòd la pa jwenn.")
    return period


def _get_employee_or_404(db: Session, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    return emp


def _viewer(db: Session, user: User) -> Optional[Employee]:
    return db.query(Employee).filter(Employee.user_id == user.id).first()


def _can_decide(db: Session, user: User, target: Employee) -> bool:
    """Menm règ ak konje yo: pa pwòp tèt ou, HR pou tout moun, manadjè pou ekip li."""
    viewer = _viewer(db, user)
    if viewer is not None and viewer.id == target.id:
        return False
    if user.role in HR_ROLES:
        return True
    if user.role != UserRole.MANAGER or viewer is None:
        return False
    return is_in_management_chain(viewer, target)


def _employed_during(period: PayPeriod):
    """Filtè: moun ki te anplwaye omwen yon jou nan peryòd la."""
    return and_(
        or_(Employee.hire_date.is_(None), Employee.hire_date <= period.end_date),
        or_(
            Employee.is_active.is_(True),
            and_(Employee.termination_date.isnot(None),
                 Employee.termination_date >= period.start_date),
        ),
    )


def _totals(db: Session, org_id: int, employee_id: int, period: PayPeriod) -> dict:
    rows = db.query(TimeEntry).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.employee_id == employee_id,
        TimeEntry.work_date >= period.start_date,
        TimeEntry.work_date <= period.end_date,
    ).all()
    counted = [r for r in rows if r.status in COUNTED_STATUSES]
    return {
        "days_present": len({r.work_date for r in rows}),
        "worked_minutes": sum(r.worked_minutes or 0 for r in counted),
        "overtime_minutes": sum(r.overtime_minutes or 0 for r in counted),
        "open_entries": sum(1 for r in rows if r.status in PROBLEM_STATUSES),
        "adjusted_entries": sum(1 for r in rows if r.status == AttendanceStatus.ADJUSTED),
    }


def _ensure_period_editable(db: Session, org_id: int, period: PayPeriod) -> None:
    if period.status != PayrollStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Pewòl peryòd sa a deja apwouve oswa peye. Èdtan yo pa ka chanje ankò.",
        )


def _upsert(db: Session, org_id: int, emp_id: int, period_id: int) -> TimesheetApproval:
    row = db.query(TimesheetApproval).filter(
        TimesheetApproval.employee_id == emp_id,
        TimesheetApproval.pay_period_id == period_id,
    ).first()
    if row is None:
        row = TimesheetApproval(organization_id=org_id, employee_id=emp_id, pay_period_id=period_id)
        db.add(row)
    return row


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

class PeriodBrief(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    pay_date: date
    status: PayrollStatus


class PeriodList(BaseModel):
    items: list[PeriodBrief]


class TimesheetRow(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    days_present: int
    worked_minutes: int
    overtime_minutes: int
    open_entries: int
    adjusted_entries: int
    status: str                       # "pending" | "approved" | "returned"
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    note: Optional[str] = None
    can_decide: bool


class PeriodTimesheets(BaseModel):
    period: PeriodBrief
    period_ended: bool
    payroll_locked: bool
    items: list[TimesheetRow]


class ApproveRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class ReturnRequest(BaseModel):
    note: str = Field(min_length=5, max_length=1000)


def _brief(p: PayPeriod) -> PeriodBrief:
    return PeriodBrief(id=p.id, name=p.name, start_date=p.start_date,
                       end_date=p.end_date, pay_date=p.pay_date, status=p.status)


# ---------------------------------------------------------------------------
# LEKTI
# ---------------------------------------------------------------------------

@router.get("/periods", response_model=PeriodList)
def list_periods(user: CurrentUser, org_id: TenantId, db: DbSession):
    """Manadjè yo pa gen aksè ak /api/payroll (salè tout moun) — men yo bezwen peryòd yo."""
    if user.role not in HR_ROLES and user.role != UserRole.MANAGER:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou paj sa a.")
    rows = db.query(PayPeriod).filter(
        PayPeriod.organization_id == org_id,
    ).order_by(PayPeriod.start_date.desc()).limit(24).all()
    return PeriodList(items=[_brief(p) for p in rows])


@router.get("/{period_id}", response_model=PeriodTimesheets)
def period_timesheets(period_id: int, user: CurrentUser, org_id: TenantId, db: DbSession):
    """
    HR wè tout moun ki te anplwaye nan peryòd la. Yon manadjè wè sèlman
    moun ki rapòte dirèkteman ba li. Pèsonn pa wè pwòp liy pa l isit la.
    """
    period = _get_period_or_404(db, org_id, period_id)

    q = db.query(Employee).filter(Employee.organization_id == org_id, _employed_during(period))
    if user.role in HR_ROLES:
        pass
    elif user.role == UserRole.MANAGER:
        viewer = _viewer(db, user)
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        q = q.filter(Employee.manager_id == viewer.id)
    else:
        raise HTTPException(status_code=403, detail="Ou pa gen dwa pou paj sa a.")

    q = q.filter(or_(Employee.user_id.is_(None), Employee.user_id != user.id))
    employees = q.order_by(Employee.last_name, Employee.first_name).all()

    approvals = {
        a.employee_id: a for a in db.query(TimesheetApproval).filter(
            TimesheetApproval.organization_id == org_id,
            TimesheetApproval.pay_period_id == period.id,
        ).all()
    }
    decider_ids = {a.decided_by_id for a in approvals.values() if a.decided_by_id}
    deciders = {
        u.id: u.full_name for u in db.query(User).filter(User.id.in_(decider_ids)).all()
    } if decider_ids else {}

    items = []
    for emp in employees:
        a = approvals.get(emp.id)
        items.append(TimesheetRow(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
            **_totals(db, org_id, emp.id, period),
            status=a.status.value if a else "pending",
            decided_by=deciders.get(a.decided_by_id) if a else None,
            decided_at=a.decided_at if a else None,
            note=a.note if a else None,
            can_decide=_can_decide(db, user, emp),
        ))

    return PeriodTimesheets(
        period=_brief(period),
        period_ended=get_local_today(db, org_id) > period.end_date,
        payroll_locked=period.status != PayrollStatus.DRAFT,
        items=items,
    )


# ---------------------------------------------------------------------------
# DESIZYON
# ---------------------------------------------------------------------------

@router.post("/{period_id}/employees/{employee_id}/approve", response_model=TimesheetRow)
def approve_timesheet(
    period_id: int,
    employee_id: int,
    payload: ApproveRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    period = _get_period_or_404(db, org_id, period_id)
    emp = _get_employee_or_404(db, org_id, employee_id)

    if not _can_decide(db, user, emp):
        raise HTTPException(status_code=403, detail="Ou pa ka apwouve èdtan moun sa a.")
    _ensure_period_editable(db, org_id, period)

    if get_local_today(db, org_id) <= period.end_date:
        raise HTTPException(
            status_code=400,
            detail=f"Peryòd la poko fini ({period.end_date:%d/%m/%Y}). "
                   "Ou ka apwouve èdtan yo sèlman apre dènye jou a.",
        )

    totals = _totals(db, org_id, emp.id, period)
    if totals["open_entries"]:
        raise HTTPException(
            status_code=400,
            detail=f"{totals['open_entries']} pwentaj toujou louvri oswa san lè sòti. "
                   "Voye fèy la bay HR pou yo korije l anvan.",
        )

    row = _upsert(db, org_id, emp.id, period.id)
    row.status = TimesheetStatus.APPROVED
    row.decided_by_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.note = payload.note
    row.worked_minutes = totals["worked_minutes"]
    row.overtime_minutes = totals["overtime_minutes"]
    db.commit()
    db.refresh(row)

    _audit(db, request, user, "approve", row.id,
           changes=f"{emp.employee_number}, peryòd #{period.id}: "
                   f"{totals['worked_minutes']} min, {totals['overtime_minutes']} min siplemantè.")

    return TimesheetRow(
        employee_id=emp.id, employee_name=f"{emp.first_name} {emp.last_name}",
        employee_number=emp.employee_number, **totals,
        status=row.status.value, decided_by=user.full_name, decided_at=row.decided_at,
        note=row.note, can_decide=True,
    )


@router.post("/{period_id}/employees/{employee_id}/return", response_model=TimesheetRow)
def return_timesheet(
    period_id: int,
    employee_id: int,
    payload: ReturnRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Manadjè a jwenn yon erè: li pa korije l limenm, li voye l bay HR ak yon nòt.
    Konsa menm moun nan pa janm chanje èdtan yo EPI apwouve yo.
    """
    period = _get_period_or_404(db, org_id, period_id)
    emp = _get_employee_or_404(db, org_id, employee_id)

    if not _can_decide(db, user, emp):
        raise HTTPException(status_code=403, detail="Ou pa ka deside sou èdtan moun sa a.")
    _ensure_period_editable(db, org_id, period)

    row = _upsert(db, org_id, emp.id, period.id)
    row.status = TimesheetStatus.RETURNED
    row.decided_by_id = user.id
    row.decided_at = datetime.now(timezone.utc)
    row.note = payload.note.strip()
    db.commit()
    db.refresh(row)

    # Avèti HR ak admin yo
    hr_users = db.query(User).filter(
        User.organization_id == org_id,
        User.role.in_([UserRole.HR, UserRole.ORG_ADMIN]),
        User.is_active.is_(True),
        User.id != user.id,
    ).all()
    for u in hr_users:
        try:
            db.add(Notification(
                organization_id=org_id, user_id=u.id, category="attendance",
                title="Èdtan pou korije",
                body=f"{user.full_name}: {emp.first_name} {emp.last_name} "
                     f"({period.name}) — {row.note}",
                link=f"/timesheets/{period.id}",
            ))
            db.commit()
        except Exception:
            db.rollback()

    _audit(db, request, user, "return", row.id, changes=row.note)

    return TimesheetRow(
        employee_id=emp.id, employee_name=f"{emp.first_name} {emp.last_name}",
        employee_number=emp.employee_number, **_totals(db, org_id, emp.id, period),
        status=row.status.value, decided_by=user.full_name, decided_at=row.decided_at,
        note=row.note, can_decide=True,
    )


@router.delete(
    "/{period_id}/employees/{employee_id}",
    dependencies=[Depends(require_hr)],
)
def reset_timesheet(
    period_id: int,
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    HR retire apwobasyon an (oswa retou a) pou li ka korije pwentaj yo.
    Manadjè a dwe apwouve ankò apre sa.
    """
    period = _get_period_or_404(db, org_id, period_id)
    _get_employee_or_404(db, org_id, employee_id)
    _ensure_period_editable(db, org_id, period)

    row = db.query(TimesheetApproval).filter(
        TimesheetApproval.organization_id == org_id,
        TimesheetApproval.pay_period_id == period.id,
        TimesheetApproval.employee_id == employee_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Pa gen desizyon pou retire.")

    before = f"{row.status.value} pa itilizatè #{row.decided_by_id}. Nòt: {row.note or '—'}"
    db.delete(row)
    db.commit()
    _audit(db, request, user, "reset", employee_id,
           changes=f"Peryòd #{period.id}. Anvan: {before}")
    return {"detail": "Desizyon an retire. Manadjè a dwe revize èdtan yo ankò."}