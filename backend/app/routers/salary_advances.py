"""
Konbit — Avans sou salè
Chemen: backend/app/routers/salary_advances.py

Endpoint yo (prefix /api/salary-advances):
    GET    /me                  Avans mwen yo (ak balans ki rete)
    POST   /me                  Mande yon avans
    POST   /me/{id}/cancel      Anile yon demann ki poko desid
    GET    ""                   Lis (manadjè: ekip dirèk li; HR: tout biznis la)
    POST   ""                   HR bay yon avans dirèk (deja apwouve)
    POST   /{id}/decide         Apwouve / refize (manadjè dirèk oswa HR)
    POST   /{id}/close          HR fèmen balans lan (rès la pa retire)

KIJAN RANBOUSMAN AN FÈT (payroll.run_payroll -> apply_advance_repayments):
  - Chak avans APWOUVE retire yon vèsman (installment_amount) sou fich la,
    jiskaske balans lan rive a 0.
  - Se yon dediksyon APRE enpo: li pa chanje brit la, ni IRI, ni ONA...
    Li sere nan payslips.advance_amount (pa nan other_deductions, pou HR
    pa efase l lè l ajiste "Lòt dediksyon").
  - Vèsman an pa janm fè net la desann anba 0. Rès la tann pwochen fich la.
  - Dènye fich yon moun ki ale (termination_date nan peryòd la): tout
    balans lan retire (toujou limite pa net la).
  - Yon avans apwouve APRE dat peman yon peryòd pa retire sou peryòd sa a.
  - Chak retrè ekri nan salary_advance_repayments (yon liy pa fich).

Yon sèl avans aktif (an atant oswa k ap ranbouse) pa moun alafwa.
Pèsonn pa ka apwouve pwòp avans li.

ATANSYON: limit legal dediksyon sou salè an Ayiti — pou verifye ak kontab la.
TOUT MONTAN AN SANTIM.
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import (
    CurrentEmployee,
    CurrentUser,
    DbSession,
    TenantId,
    require_hr,
    require_manager,
)
from ..models import (
    AuditLog,
    Employee,
    Notification,
    PayPeriod,
    SalaryAdvance,
    SalaryAdvanceRepayment,
    User,
    UserRole,
)
from ..timezone_utils import get_org_timezone

logger = logging.getLogger("konbit")

router = APIRouter()

PENDING = "pending"
APPROVED = "approved"      # k ap ranbouse
REPAID = "repaid"          # fin ranbouse
REJECTED = "rejected"
CANCELLED = "cancelled"    # anplwaye a anile demann lan
CLOSED = "closed"          # HR fèmen balans lan

ACTIVE_STATUSES = (PENDING, APPROVED)
HR_ROLES = (UserRole.HR, UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN)
MAX_INSTALLMENTS = 12


# ---------------------------------------------------------------------------
# KALKIL (fonksyon pi — teste nan test_salary_advance_plan.py)
# ---------------------------------------------------------------------------

def installment_for(amount: int, installments: int) -> int:
    """Vèsman pa peryòd, awondi anwo: 3 × 333 334 kouvri 1 000 000."""
    return -(-amount // max(1, installments))


def plan_repayments(
    balances: list[tuple[int, int]],
    available: int,
    settle_all: bool,
) -> list[int]:
    """
    Konbyen pou retire sou chak avans pou YON fich.

    `balances`  : [(balans ki rete, vèsman)] nan lòd apwobasyon (pi ansyen an premye)
    `available` : net fich la anvan avans yo — nou pa janm depase l
    `settle_all`: dènye fich (moun nan ap kite): tout balans lan, pa yon vèsman
    """
    left = max(0, available)
    plan = []
    for remaining, installment in balances:
        want = remaining if settle_all else min(installment, remaining)
        take = max(0, min(want, left))
        plan.append(take)
        left -= take
    return plan


def repaid_amounts(db: Session, advance_ids: list[int]) -> dict[int, int]:
    """Total ki deja retire pou chak avans."""
    if not advance_ids:
        return {}
    rows = (
        db.query(
            SalaryAdvanceRepayment.advance_id,
            func.coalesce(func.sum(SalaryAdvanceRepayment.amount), 0),
        )
        .filter(SalaryAdvanceRepayment.advance_id.in_(advance_ids))
        .group_by(SalaryAdvanceRepayment.advance_id)
        .all()
    )
    return {advance_id: int(total or 0) for advance_id, total in rows}


def _local_day(when: Optional[datetime], tz) -> Optional[date]:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(tz).date()


def _money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def apply_advance_repayments(db: Session, org_id: int, emp: Employee, slip, period) -> Optional[str]:
    """
    Retire vèsman avans yo sou yon fich ki fèk kreye (payroll.run_payroll).
    `slip` dwe gen yon id deja (db.flush). Mete slip.advance_amount epi
    redui slip.net_amount. Retounen yon avètisman pou HR, oswa None.
    """
    tz = get_org_timezone(db, org_id)
    advances = [
        a for a in db.query(SalaryAdvance).filter(
            SalaryAdvance.organization_id == org_id,
            SalaryAdvance.employee_id == emp.id,
            SalaryAdvance.status == APPROVED,
        ).order_by(SalaryAdvance.decided_at, SalaryAdvance.id).all()
        if (_local_day(a.decided_at, tz) or period.pay_date) <= period.pay_date
    ]

    slip.advance_amount = 0
    if not advances:
        return None

    repaid = repaid_amounts(db, [a.id for a in advances])
    remaining = [max(0, a.amount - repaid.get(a.id, 0)) for a in advances]
    leaving = emp.termination_date is not None and emp.termination_date <= period.end_date
    wanted = [r if leaving else min(a.installment_amount, r) for a, r in zip(advances, remaining)]
    plan = plan_repayments(
        [(r, a.installment_amount) for a, r in zip(advances, remaining)],
        slip.net_amount or 0,
        leaving,
    )

    now = datetime.now(timezone.utc)
    total = 0
    for adv, rem, take in zip(advances, remaining, plan):
        if take > 0:
            db.add(SalaryAdvanceRepayment(
                organization_id=org_id,
                advance_id=adv.id,
                employee_id=emp.id,
                payslip_id=slip.id,
                pay_period_id=period.id,
                amount=take,
            ))
            total += take
        if rem - take <= 0:
            adv.status = REPAID
            adv.closed_at = now

    slip.advance_amount = total
    slip.net_amount = max(0, (slip.net_amount or 0) - total)

    notes = []
    missing = sum(wanted) - total
    if leaving and total:
        notes.append(f"dènye fich: balans avans lan retire ({_money(total)}).")
    if missing > 0:
        if leaving:
            notes.append(f"net la pa ase: {_money(missing)} avans pa ka retire — pale ak kontab la.")
        else:
            notes.append(f"net la pa ase: {_money(missing)} avans ap retire sou pwochen fich yo.")
    return " ".join(notes) or None


# ---------------------------------------------------------------------------
# SCHEMAS
# ---------------------------------------------------------------------------

class AdvanceRequest(BaseModel):
    amount: int = Field(gt=0, le=100_000_000, description="An santim")
    installments: int = Field(default=1, ge=1, le=MAX_INSTALLMENTS)
    reason: Optional[str] = Field(default=None, max_length=500)


class AdvanceGrant(AdvanceRequest):
    employee_id: int


class AdvanceDecision(BaseModel):
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


class AdvanceClose(BaseModel):
    note: str = Field(min_length=3, max_length=500)


class RepaymentOut(BaseModel):
    pay_period_id: int
    period_name: str
    amount: int
    created_at: datetime


class AdvanceOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_number: str
    amount: int
    installments: int
    installment_amount: int
    repaid_amount: int
    remaining_amount: int          # 0 si refize / anile / fèmen / fin ranbouse
    currency: str
    reason: Optional[str] = None
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    repayments: list[RepaymentOut] = []


class AdvanceList(BaseModel):
    total: int
    items: list[AdvanceOut]


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
            entity_type="salary_advance",
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _notify(db: Session, org_id: int, user_id: Optional[int],
            title: str, body: str, link: Optional[str] = None) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id, user_id=user_id,
            title=title, body=body, link_url=link, category="payroll",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _my_employee(db: Session, org_id: int, user: User) -> Optional[Employee]:
    return db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.user_id == user.id,
    ).first()


def _get_or_404(db: Session, org_id: int, advance_id: int) -> tuple[SalaryAdvance, Employee]:
    row = (
        db.query(SalaryAdvance, Employee)
        .join(Employee, Employee.id == SalaryAdvance.employee_id)
        .filter(SalaryAdvance.id == advance_id, SalaryAdvance.organization_id == org_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404)
    return row


def _ensure_can_decide(db: Session, org_id: int, user: User, emp: Employee) -> None:
    """Manadjè dirèk la oswa HR. Pèsonn pa janm desid pwòp avans li."""
    if emp.user_id is not None and emp.user_id == user.id:
        raise HTTPException(status_code=403, detail="Ou pa ka apwouve pwòp avans ou.")
    if user.role in HR_ROLES:
        return
    me = _my_employee(db, org_id, user)
    if me is None or emp.manager_id != me.id:
        raise HTTPException(status_code=404)


def _check_new(db: Session, org_id: int, emp: Employee, amount: int) -> None:
    if not emp.on_payroll or not emp.is_active:
        raise HTTPException(
            status_code=400,
            detail="Moun sa a pa sou pewòl: li pa ka resevwa yon avans.",
        )
    active = db.query(SalaryAdvance.id).filter(
        SalaryAdvance.organization_id == org_id,
        SalaryAdvance.employee_id == emp.id,
        SalaryAdvance.status.in_(ACTIVE_STATUSES),
    ).first()
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Gen yon avans ki poko fin ranbouse (oswa ki an atant) pou moun sa a.",
        )
    if emp.base_salary and amount > emp.base_salary:
        raise HTTPException(
            status_code=400,
            detail=f"Avans lan pa ka depase salè yon peryòd ({_money(emp.base_salary)}).",
        )


def _approver_user_ids(db: Session, org_id: int, emp: Employee) -> list[int]:
    """Manadjè dirèk la; si pa genyen, moun HR yo."""
    if emp.manager_id:
        manager = db.query(Employee).filter(Employee.id == emp.manager_id).first()
        if manager and manager.user_id and manager.user_id != emp.user_id:
            return [manager.user_id]
    rows = db.query(User.id).filter(
        User.organization_id == org_id,
        User.role.in_([UserRole.HR, UserRole.ORG_ADMIN]),
        User.is_active.is_(True),
    ).limit(20).all()
    return [r[0] for r in rows if r[0] != emp.user_id]


def _out(db: Session, adv: SalaryAdvance, emp: Employee) -> AdvanceOut:
    rows = (
        db.query(SalaryAdvanceRepayment, PayPeriod.name)
        .join(PayPeriod, PayPeriod.id == SalaryAdvanceRepayment.pay_period_id)
        .filter(SalaryAdvanceRepayment.advance_id == adv.id)
        .order_by(SalaryAdvanceRepayment.id)
        .all()
    )
    paid = sum(r.amount for r, _ in rows)
    remaining = max(0, adv.amount - paid) if adv.status in ACTIVE_STATUSES else 0
    return AdvanceOut(
        id=adv.id,
        employee_id=emp.id,
        employee_name=f"{emp.first_name} {emp.last_name}",
        employee_number=emp.employee_number,
        amount=adv.amount,
        installments=adv.installments,
        installment_amount=adv.installment_amount,
        repaid_amount=paid,
        remaining_amount=remaining,
        currency=emp.currency.value if emp.currency else "HTG",
        reason=adv.reason,
        status=adv.status,
        created_at=adv.created_at,
        decided_at=adv.decided_at,
        decision_note=adv.decision_note,
        repayments=[
            RepaymentOut(pay_period_id=r.pay_period_id, period_name=name,
                         amount=r.amount, created_at=r.created_at)
            for r, name in rows
        ],
    )


# ---------------------------------------------------------------------------
# ANPLWAYE A
# ---------------------------------------------------------------------------

@router.get("/me", response_model=AdvanceList)
def my_advances(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    items = db.query(SalaryAdvance).filter(
        SalaryAdvance.organization_id == org_id,
        SalaryAdvance.employee_id == emp.id,
    ).order_by(SalaryAdvance.created_at.desc(), SalaryAdvance.id.desc()).limit(50).all()
    return AdvanceList(total=len(items), items=[_out(db, a, emp) for a in items])


@router.post("/me", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def request_advance(
    payload: AdvanceRequest,
    emp: CurrentEmployee,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    _check_new(db, org_id, emp, payload.amount)
    adv = SalaryAdvance(
        organization_id=org_id,
        employee_id=emp.id,
        requested_by_id=user.id,
        amount=payload.amount,
        installments=payload.installments,
        installment_amount=installment_for(payload.amount, payload.installments),
        reason=(payload.reason or "").strip() or None,
        status=PENDING,
    )
    db.add(adv)
    db.commit()
    db.refresh(adv)

    _audit(db, request, user, "request", adv.id,
           changes=f"{adv.amount} santim, {adv.installments} vèsman.")
    for uid in _approver_user_ids(db, org_id, emp):
        _notify(db, org_id, uid,
                title="Demann avans sou salè",
                body=f"{emp.first_name} {emp.last_name} mande {_money(adv.amount)} "
                     f"sou {adv.installments} vèsman.",
                link="salary-advances.html")
    return _out(db, adv, emp)


@router.post("/me/{advance_id}/cancel", response_model=AdvanceOut)
def cancel_my_request(
    advance_id: int,
    emp: CurrentEmployee,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    adv, owner = _get_or_404(db, org_id, advance_id)
    if owner.id != emp.id:
        raise HTTPException(status_code=404)
    if adv.status != PENDING:
        raise HTTPException(status_code=400, detail="Sèlman yon demann an atant ka anile.")
    adv.status = CANCELLED
    adv.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(adv)
    _audit(db, request, user, "cancel", adv.id)
    return _out(db, adv, emp)


# ---------------------------------------------------------------------------
# MANADJÈ AK HR
# ---------------------------------------------------------------------------

@router.get("", response_model=AdvanceList, dependencies=[Depends(require_manager)])
def list_advances(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[str], Query(
        alias="status", pattern="^(pending|approved|repaid|rejected|cancelled|closed)$",
    )] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    """HR wè tout biznis la; yon manadjè wè sèlman moun ki rapòte dirèkteman ba li."""
    q = (
        db.query(SalaryAdvance, Employee)
        .join(Employee, Employee.id == SalaryAdvance.employee_id)
        .filter(SalaryAdvance.organization_id == org_id)
    )
    if user.role not in HR_ROLES:
        me = _my_employee(db, org_id, user)
        if me is None:
            return AdvanceList(total=0, items=[])
        q = q.filter(Employee.manager_id == me.id)
    if status_filter:
        q = q.filter(SalaryAdvance.status == status_filter)

    rows = q.order_by(SalaryAdvance.created_at.desc(), SalaryAdvance.id.desc()).limit(limit).all()
    return AdvanceList(total=len(rows), items=[_out(db, a, e) for a, e in rows])


@router.post(
    "",
    response_model=AdvanceOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def grant_advance(
    payload: AdvanceGrant,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """HR anrejistre yon avans ki deja bay (egz: patwon an bay kach). Li apwouve dirèk."""
    emp = db.query(Employee).filter(
        Employee.id == payload.employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404)
    if emp.user_id is not None and emp.user_id == user.id:
        raise HTTPException(status_code=403, detail="Yon lòt moun dwe apwouve pwòp avans ou.")
    _check_new(db, org_id, emp, payload.amount)

    now = datetime.now(timezone.utc)
    adv = SalaryAdvance(
        organization_id=org_id,
        employee_id=emp.id,
        requested_by_id=user.id,
        amount=payload.amount,
        installments=payload.installments,
        installment_amount=installment_for(payload.amount, payload.installments),
        reason=(payload.reason or "").strip() or None,
        status=APPROVED,
        decided_by_id=user.id,
        decided_at=now,
    )
    db.add(adv)
    db.commit()
    db.refresh(adv)

    _audit(db, request, user, "grant", adv.id,
           changes=f"{adv.amount} santim, {adv.installments} vèsman, pou anplwaye {emp.id}.")
    _notify(db, org_id, emp.user_id,
            title="Avans sou salè anrejistre",
            body=f"Avans {_money(adv.amount)}: {adv.installments} vèsman "
                 f"{_money(adv.installment_amount)} ap retire sou fich peye w yo.",
            link="dashboard.html#avans")
    return _out(db, adv, emp)


@router.post("/{advance_id}/decide", response_model=AdvanceOut, dependencies=[Depends(require_manager)])
def decide_advance(
    advance_id: int,
    payload: AdvanceDecision,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    adv, emp = _get_or_404(db, org_id, advance_id)
    _ensure_can_decide(db, org_id, user, emp)
    if adv.status != PENDING:
        raise HTTPException(status_code=400, detail=f"Demann lan nan estati '{adv.status}'.")

    if payload.approve:
        other = db.query(SalaryAdvance.id).filter(
            SalaryAdvance.organization_id == org_id,
            SalaryAdvance.employee_id == emp.id,
            SalaryAdvance.status == APPROVED,
            SalaryAdvance.id != adv.id,
        ).first()
        if other:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Moun sa a gen yon lòt avans k ap ranbouse deja.",
            )

    now = datetime.now(timezone.utc)
    adv.status = APPROVED if payload.approve else REJECTED
    adv.decided_by_id = user.id
    adv.decided_at = now
    adv.decision_note = (payload.note or "").strip() or None
    if not payload.approve:
        adv.closed_at = now
    db.commit()
    db.refresh(adv)

    _audit(db, request, user, "approve" if payload.approve else "reject", adv.id,
           changes=f"Nòt: {adv.decision_note or '—'}")
    _notify(
        db, org_id, emp.user_id,
        title="Avans ou apwouve" if payload.approve else "Avans ou refize",
        body=(f"{_money(adv.amount)}: {adv.installments} vèsman {_money(adv.installment_amount)} "
              "ap retire sou fich peye w yo."
              if payload.approve else
              f"Demann {_money(adv.amount)} lan refize."
              + (f" « {adv.decision_note} »" if adv.decision_note else "")),
        link="dashboard.html#avans",
    )
    return _out(db, adv, emp)


@router.post("/{advance_id}/close", response_model=AdvanceOut, dependencies=[Depends(require_hr)])
def close_advance(
    advance_id: int,
    payload: AdvanceClose,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    HR fèmen yon avans: rès balans lan p ap retire ankò (padon, antant apa...).
    Retrè ki deja fèt sou fich yo rete. Nòt la obligatwa (jounal odit).
    """
    adv, emp = _get_or_404(db, org_id, advance_id)
    if emp.user_id is not None and emp.user_id == user.id:
        raise HTTPException(status_code=403, detail="Yon lòt moun dwe fèmen pwòp avans ou.")
    if adv.status != APPROVED:
        raise HTTPException(status_code=400, detail="Sèlman yon avans k ap ranbouse ka fèmen.")

    left = max(0, adv.amount - repaid_amounts(db, [adv.id]).get(adv.id, 0))
    adv.status = CLOSED
    adv.closed_at = datetime.now(timezone.utc)
    note = payload.note.strip()
    adv.decision_note = f"{adv.decision_note}\n{note}" if adv.decision_note else note
    db.commit()
    db.refresh(adv)

    _audit(db, request, user, "close", adv.id,
           changes=f"Balans fèmen: {left} santim pa retire. Nòt: {note}")
    return _out(db, adv, emp)