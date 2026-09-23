"""
Konbit — Router Konje
Chemen: backend/app/routers/leaves.py

Endpoint yo:
    POST   /api/leaves                     Fè yon demann konje
    GET    /api/leaves/me                  Pwòp demann mwen
    GET    /api/leaves/me/balances         Balans konje mwen
    DELETE /api/leaves/{id}                Anile pwòp demann mwen
    GET    /api/leaves/pending             Demann k ap tann apwobasyon m
    POST   /api/leaves/{id}/decide         Apwouve oswa refize
    GET    /api/leaves/calendar            Kiyès ki an konje nan yon peryòd
    GET    /api/leaves/employee/{id}       Demann yon anplwaye
    GET    /api/leaves/employee/{id}/balances
    PUT    /api/leaves/balances            HR mete balans yo (chak ane)
    GET    /api/leaves/balances            Lis balans TOUT anplwaye pou HR (paj Balans konje)

RÈG APWOBASYON: se manadjè dirèk la ki apwouve. HR ak ORG_ADMIN ka apwouve
nenpòt demann. Yon moun pa ka apwouve pwòp demann pa l.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    is_in_management_chain,
    require_hr,
)
from ..models import (
    AuditLog,
    Employee,
    EmploymentStatus,
    LeaveBalance,
    LeaveRequest,
    LeaveType,
    Notification,
    RequestStatus,
    User,
    UserRole,
)
from ..schemas import (
    LeaveBalanceOut,
    LeaveDecision,
    LeaveRequestCreate,
    LeaveRequestOut,
    Message,
)
from ..timezone_utils import get_local_today

logger = logging.getLogger("konbit")

router = APIRouter()

# Konje ki pa rache nan balans lan
NON_DEDUCTIBLE = {LeaveType.UNPAID, LeaveType.BEREAVEMENT, LeaveType.OTHER}


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
            entity_type="leave_request",
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _notify(db: Session, org_id: int, user_id: Optional[int], title: str,
            body: str, link: Optional[str] = None) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id,
            user_id=user_id,
            title=title,
            body=body,
            link_url=link,
            category="leave",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _business_days(start: date, end: date) -> Decimal:
    """
    Konte jou travay (lendi–vandredi). Nou pa konte samdi ak dimanch.
    NÒT: jou ferye ayisyen yo pa nan kalkil la pou kounye a — sa mande
    yon tab `holidays` pa òganizasyon.
    """
    days = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return Decimal(days)


def _get_employee_or_404(db: Session, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    return emp


def _get_request_or_404(db: Session, org_id: int, request_id: int) -> LeaveRequest:
    req = db.query(LeaveRequest).filter(
        LeaveRequest.id == request_id,
        LeaveRequest.organization_id == org_id,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Demann lan pa jwenn.")
    return req


def _get_or_create_balance(db: Session, org_id: int, employee_id: int,
                           leave_type: LeaveType, year: int) -> LeaveBalance:
    bal = db.query(LeaveBalance).filter(
        LeaveBalance.organization_id == org_id,
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.leave_type == leave_type,
        LeaveBalance.year == year,
    ).first()
    if bal is None:
        bal = LeaveBalance(
            organization_id=org_id,
            employee_id=employee_id,
            leave_type=leave_type,
            year=year,
            entitled_days=Decimal(0),
            used_days=Decimal(0),
            carried_over_days=Decimal(0),
        )
        db.add(bal)
        db.flush()
    return bal


def _has_overlap(db: Session, org_id: int, employee_id: int,
                 start: date, end: date, exclude_id: Optional[int] = None) -> bool:
    """Anpeche de demann sou menm jou yo."""
    q = db.query(LeaveRequest).filter(
        LeaveRequest.organization_id == org_id,
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_([RequestStatus.PENDING, RequestStatus.APPROVED]),
        and_(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start),
    )
    if exclude_id:
        q = q.filter(LeaveRequest.id != exclude_id)
    return q.first() is not None


def _can_decide(db: Session, user: User, req: LeaveRequest) -> bool:
    """HR ak admin ka apwouve tout. Yon manadjè sèlman moun ki anba l."""
    if user.role in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR):
        return True
    if user.role != UserRole.MANAGER:
        return False

    approver = db.query(Employee).filter(Employee.user_id == user.id).first()
    if approver is None:
        return False
    if approver.id == req.employee_id:
        return False        # pa ka apwouve pwòp demann ou

    target = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if target is None:
        return False
    return is_in_management_chain(approver, target)


# ---------------------------------------------------------------------------
# FÈ YON DEMANN
# ---------------------------------------------------------------------------

@router.post("", response_model=LeaveRequestOut, status_code=status.HTTP_201_CREATED)
def create_leave_request(
    payload: LeaveRequestCreate,
    emp: CurrentEmployee,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    if emp.status != EmploymentStatus.ACTIVE:
        raise HTTPException(
            status_code=403,
            detail="Ou pa ka fè demann konje: estati w se pa aktif.",
        )

    if _has_overlap(db, org_id, emp.id, payload.start_date, payload.end_date):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ou gen yon demann ki kouvri menm jou sa yo deja.",
        )

    total_days = _business_days(payload.start_date, payload.end_date)
    if total_days == 0:
        raise HTTPException(
            status_code=400,
            detail="Peryòd la pa gen okenn jou travay (sèlman wikenn).",
        )

    # Verifye balans lan si se yon konje ki rache
    if payload.leave_type not in NON_DEDUCTIBLE:
        year = payload.start_date.year
        bal = db.query(LeaveBalance).filter(
            LeaveBalance.organization_id == org_id,
            LeaveBalance.employee_id == emp.id,
            LeaveBalance.leave_type == payload.leave_type,
            LeaveBalance.year == year,
        ).first()
        if bal is not None:
            remaining = (
                Decimal(bal.entitled_days or 0)
                + Decimal(bal.carried_over_days or 0)
                - Decimal(bal.used_days or 0)
            )
            if total_days > remaining:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Ou mande {total_days} jou men ou gen sèlman "
                        f"{remaining} jou ki rete."
                    ),
                )

    req = LeaveRequest(
        organization_id=org_id,
        employee_id=emp.id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        total_days=total_days,
        reason=payload.reason,
        attachment_url=payload.attachment_url,
        status=RequestStatus.PENDING,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Avèti manadjè a
    if emp.manager_id:
        manager = db.query(Employee).filter(Employee.id == emp.manager_id).first()
        if manager and manager.user_id:
            _notify(
                db, org_id, manager.user_id,
                title="Nouvo demann konje",
                body=f"{emp.first_name} {emp.last_name} mande {total_days} jou konje.",
                link=f"/leaves/{req.id}",
            )

    return req


# ---------------------------------------------------------------------------
# PWÒP DEMANN MWEN
# ---------------------------------------------------------------------------

class LeaveList(BaseModel):
    total: int
    items: list[LeaveRequestOut]


@router.get("/me", response_model=LeaveList)
def my_requests(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[RequestStatus], Query(alias="status")] = None,
    year: Optional[int] = None,
):
    q = db.query(LeaveRequest).filter(
        LeaveRequest.organization_id == org_id,
        LeaveRequest.employee_id == emp.id,
    )
    if status_filter:
        q = q.filter(LeaveRequest.status == status_filter)
    if year:
        q = q.filter(
            LeaveRequest.start_date >= date(year, 1, 1),
            LeaveRequest.start_date <= date(year, 12, 31),
        )

    items = q.order_by(LeaveRequest.start_date.desc()).all()
    return LeaveList(total=len(items), items=[LeaveRequestOut.model_validate(i) for i in items])


@router.delete("/{request_id}", response_model=Message)
def cancel_my_request(
    request_id: int,
    emp: CurrentEmployee,
    org_id: TenantId,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    """
    Anile pwòp demann ou. Si li te deja apwouve, jou yo retounen nan balans lan.
    Nou pa efase liy lan — nou make l CANCELLED.
    """
    req = _get_request_or_404(db, org_id, request_id)

    if req.employee_id != emp.id:
        raise HTTPException(status_code=403, detail="Se pa demann ou.")
    if req.status == RequestStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Demann lan deja anile.")
    if req.start_date < get_local_today(db, org_id) and req.status == RequestStatus.APPROVED:
        raise HTTPException(
            status_code=400,
            detail="Ou pa ka anile yon konje ki deja kòmanse. Pale ak HR.",
        )

    was_approved = req.status == RequestStatus.APPROVED
    req.status = RequestStatus.CANCELLED

    if was_approved and req.leave_type not in NON_DEDUCTIBLE:
        bal = _get_or_create_balance(
            db, org_id, req.employee_id, req.leave_type, req.start_date.year
        )
        bal.used_days = max(Decimal(0), Decimal(bal.used_days or 0) - Decimal(req.total_days))

    db.commit()
    _audit(db, request, user, "cancel", req.id)
    return Message(detail="Demann lan anile.")


# ---------------------------------------------------------------------------
# APWOBASYON
# ---------------------------------------------------------------------------

class PendingItem(BaseModel):
    request: LeaveRequestOut
    employee_name: str
    employee_number: str


class PendingList(BaseModel):
    total: int
    items: list[PendingItem]


@router.get("/pending", response_model=PendingList)
def pending_for_me(user: CurrentUser, org_id: TenantId, db: DbSession):
    """Demann k ap tann desizyon mwen."""
    q = (
        db.query(LeaveRequest, Employee)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .filter(
            LeaveRequest.organization_id == org_id,
            LeaveRequest.status == RequestStatus.PENDING,
        )
    )

    if user.role == UserRole.MANAGER:
        approver = db.query(Employee).filter(Employee.user_id == user.id).first()
        if approver is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        q = q.filter(Employee.manager_id == approver.id)
    elif user.role not in (UserRole.SUPER_ADMIN, UserRole.ORG_ADMIN, UserRole.HR):
        return PendingList(total=0, items=[])

    rows = q.order_by(LeaveRequest.start_date).all()
    items = [
        PendingItem(
            request=LeaveRequestOut.model_validate(req),
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
        )
        for req, emp in rows
    ]
    return PendingList(total=len(items), items=items)


@router.post("/{request_id}/decide", response_model=LeaveRequestOut)
def decide_request(
    request_id: int,
    payload: LeaveDecision,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    req = _get_request_or_404(db, org_id, request_id)

    if req.status != RequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Demann lan deja nan estati '{req.status.value}'.",
        )

    if not _can_decide(db, user, req):
        raise HTTPException(
            status_code=403,
            detail="Ou pa gen dwa pou deside sou demann sa a.",
        )

    approver = db.query(Employee).filter(Employee.user_id == user.id).first()

    req.status = RequestStatus.APPROVED if payload.approve else RequestStatus.REJECTED
    req.approver_id = approver.id if approver else None
    req.approved_at = datetime.now(timezone.utc)
    req.decision_note = payload.note

    # Rache jou yo nan balans lan sèlman lè demann lan apwouve
    if payload.approve and req.leave_type not in NON_DEDUCTIBLE:
        bal = _get_or_create_balance(
            db, org_id, req.employee_id, req.leave_type, req.start_date.year
        )
        bal.used_days = Decimal(bal.used_days or 0) + Decimal(req.total_days)

    db.commit()
    db.refresh(req)

    target = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if target and target.user_id:
        _notify(
            db, org_id, target.user_id,
            title="Repons sou demann konje w",
            body=(
                f"Demann {req.total_days} jou w la "
                f"{'apwouve' if payload.approve else 'refize'}."
            ),
            link=f"/leaves/{req.id}",
        )

    _audit(db, request, user, "decide", req.id,
           changes=f"{req.status.value}. Nòt: {payload.note or '—'}")
    return req


# ---------------------------------------------------------------------------
# KALANDRIYE
# ---------------------------------------------------------------------------

class CalendarItem(BaseModel):
    employee_id: int
    employee_name: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    total_days: float


class LeaveCalendar(BaseModel):
    period_start: date
    period_end: date
    total: int
    items: list[CalendarItem]


@router.get("/calendar", response_model=LeaveCalendar)
def leave_calendar(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    department_id: Optional[int] = None,
):
    """
    Kiyès ki an konje nan yon peryòd. Tout anplwaye ka wè l — li ede moun
    planifye. Rezon konje a PA parèt (li ka medikal oswa prive).
    """
    start = start_date or get_local_today(db, org_id)
    end = end_date or (start + timedelta(days=30))

    q = (
        db.query(LeaveRequest, Employee)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .filter(
            LeaveRequest.organization_id == org_id,
            LeaveRequest.status == RequestStatus.APPROVED,
            and_(LeaveRequest.start_date <= end, LeaveRequest.end_date >= start),
        )
    )
    if department_id is not None:
        q = q.filter(Employee.department_id == department_id)

    rows = q.order_by(LeaveRequest.start_date).all()
    items = [
        CalendarItem(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            leave_type=req.leave_type,
            start_date=req.start_date,
            end_date=req.end_date,
            total_days=float(req.total_days),
        )
        for req, emp in rows
    ]

    return LeaveCalendar(
        period_start=start, period_end=end, total=len(items), items=items
    )


# ---------------------------------------------------------------------------
# BALANS
# ---------------------------------------------------------------------------

class BalanceItem(BaseModel):
    leave_type: LeaveType
    year: int
    entitled_days: float
    carried_over_days: float
    used_days: float
    remaining_days: float


class BalanceList(BaseModel):
    employee_id: int
    year: int
    balances: list[BalanceItem]


def _balances_for(db: Session, org_id: int, employee_id: int, year: int) -> BalanceList:
    rows = db.query(LeaveBalance).filter(
        LeaveBalance.organization_id == org_id,
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.year == year,
    ).all()

    balances = []
    for b in rows:
        entitled = float(b.entitled_days or 0)
        carried = float(b.carried_over_days or 0)
        used = float(b.used_days or 0)
        balances.append(BalanceItem(
            leave_type=b.leave_type,
            year=b.year,
            entitled_days=entitled,
            carried_over_days=carried,
            used_days=used,
            remaining_days=entitled + carried - used,
        ))

    return BalanceList(employee_id=employee_id, year=year, balances=balances)


@router.get("/me/balances", response_model=BalanceList)
def my_balances(
    emp: CurrentEmployee,
    org_id: TenantId,
    db: DbSession,
    year: Optional[int] = None,
):
    return _balances_for(db, org_id, emp.id, year or get_local_today(db, org_id).year)


@router.get("/employee/{employee_id}/balances", response_model=BalanceList)
def employee_balances(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    year: Optional[int] = None,
):
    target = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, target, db)
    return _balances_for(db, org_id, employee_id, year or get_local_today(db, org_id).year)


@router.get("/employee/{employee_id}", response_model=LeaveList)
def employee_requests(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[RequestStatus], Query(alias="status")] = None,
):
    target = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, target, db)

    q = db.query(LeaveRequest).filter(
        LeaveRequest.organization_id == org_id,
        LeaveRequest.employee_id == employee_id,
    )
    if status_filter:
        q = q.filter(LeaveRequest.status == status_filter)

    items = q.order_by(LeaveRequest.start_date.desc()).all()
    return LeaveList(total=len(items), items=[LeaveRequestOut.model_validate(i) for i in items])


class SetBalanceRequest(BaseModel):
    employee_id: int
    leave_type: LeaveType
    year: int = Field(ge=2020, le=2100)
    entitled_days: float = Field(ge=0, le=365)
    carried_over_days: float = Field(default=0, ge=0, le=365)


@router.put("/balances", response_model=BalanceItem, dependencies=[Depends(require_hr)])
def set_balance(
    payload: SetBalanceRequest,
    org_id: TenantId,
    db: DbSession,
):
    """
    HR mete konbyen jou yon anplwaye gen dwa pou yon ane.
    An Ayiti, Kòd Travay la bay 15 jou konje anyèl apre yon ane sèvis.
    """
    _get_employee_or_404(db, org_id, payload.employee_id)

    bal = _get_or_create_balance(
        db, org_id, payload.employee_id, payload.leave_type, payload.year
    )
    bal.entitled_days = Decimal(str(payload.entitled_days))
    bal.carried_over_days = Decimal(str(payload.carried_over_days))
    db.commit()
    db.refresh(bal)

    entitled = float(bal.entitled_days or 0)
    carried = float(bal.carried_over_days or 0)
    used = float(bal.used_days or 0)
    return BalanceItem(
        leave_type=bal.leave_type,
        year=bal.year,
        entitled_days=entitled,
        carried_over_days=carried,
        used_days=used,
        remaining_days=entitled + carried - used,
    )


class OrgBalanceItem(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    entitled_days: float
    carried_over_days: float
    used_days: float
    remaining_days: float


class OrgBalanceList(BaseModel):
    total: int
    leave_type: LeaveType
    year: int
    items: list[OrgBalanceItem]


@router.get("/balances", response_model=OrgBalanceList, dependencies=[Depends(require_hr)])
def list_org_balances(
    org_id: TenantId,
    db: DbSession,
    leave_type: LeaveType = LeaveType.VACATION,
    year: Optional[int] = None,
    q: Annotated[Optional[str], Query(description="Rechèch sou non oswa nimewo")] = None,
    include_inactive: bool = False,
):
    """
    Lis balans TOUT anplwaye pou yon kalite konje ak yon ane — pou paj
    "Balans konje" HR la. Nou fè sa an de rekèt sèlman (anplwaye, epi
    balans yo), pa yon rekèt pa moun, menm jan ak /hierarchy/tree, pou
    evite N+1 sou yon biznis ak anpil anplwaye.

    Si yon anplwaye poko gen yon ranje LeaveBalance pou (kalite, ane) sa
    a, li parèt ak 0 jou — HR ka kreye l lè li sove yon valè nan paj la.
    """
    yr = year or get_local_today(db, org_id).year

    emp_q = db.query(Employee).filter(Employee.organization_id == org_id)
    if not include_inactive:
        emp_q = emp_q.filter(Employee.is_active.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        emp_q = emp_q.filter(or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_number.ilike(pattern),
        ))
    employees = emp_q.order_by(Employee.last_name, Employee.first_name).all()

    bal_by_emp = {
        b.employee_id: b
        for b in db.query(LeaveBalance).filter(
            LeaveBalance.organization_id == org_id,
            LeaveBalance.leave_type == leave_type,
            LeaveBalance.year == yr,
        ).all()
    }

    items = []
    for emp in employees:
        b = bal_by_emp.get(emp.id)
        entitled = float(b.entitled_days or 0) if b else 0.0
        carried = float(b.carried_over_days or 0) if b else 0.0
        used = float(b.used_days or 0) if b else 0.0
        items.append(OrgBalanceItem(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            employee_number=emp.employee_number,
            entitled_days=entitled,
            carried_over_days=carried,
            used_days=used,
            remaining_days=entitled + carried - used,
        ))

    return OrgBalanceList(total=len(items), leave_type=leave_type, year=yr, items=items)