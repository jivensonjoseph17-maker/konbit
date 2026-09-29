"""
Konbit — Demann chanjman peman (kont labank / MonCash / NatCash)
Chemen: backend/app/routers/payment_changes.py

    GET  /api/payment-changes/me               Demann mwen yo
    POST /api/payment-changes/me               Voye yon demann (modpas obligatwa)
    POST /api/payment-changes/me/{id}/cancel   Anile pwòp demann mwen (si l ap tann)
    GET  /api/payment-changes                  Lis pou HR (?status=pending pa defo)
    POST /api/payment-changes/{id}/decide      HR apwouve / refize

POUKISA YON DEMANN, PA YON CHANJMAN DIRÈK:
Si yon moun vòlè sesyon yon anplwaye (telefòn prete, òdinatè piblik), li ta ka
mete PWÒP nimewo MonCash li epi pran pwochen salè a. Kounye a:
  1. anplwaye a dwe retape modpas li (yon sesyon vòlè pa sifi);
  2. yon moun HR dwe apwouve — e pèsonn pa apwouve pwòp demann li;
  3. HR wè sèlman 4 dènye chif yo; chak etap ale nan jounal odit la.

Yon demann apwouve chanje dosye anplwaye a pou PWOCHEN pewòl yo. Fich ki
deja kalkile yo kenbe metòd yo te genyen an.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..deps import CurrentEmployee, CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    AuditLog, Employee, Notification, PaymentChangeRequest, PaymentMethod, User, UserRole,
)
from ..security import verify_password

logger = logging.getLogger("konbit")

router = APIRouter()

Method = Literal["check", "direct_deposit", "cash", "moncash", "natcash"]
StatusFilter = Literal["pending", "approved", "rejected", "cancelled", "all"]

MOBILE = ("moncash", "natcash")


# ---------------------------------------------------------------------------
# ZOUTI
# ---------------------------------------------------------------------------

def _last4(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value[-4:] if len(value) >= 4 else None


def _current(emp: Employee) -> tuple[str, Optional[str], Optional[str]]:
    """(metòd, bank, 4 dènye chif) anplwaye a jodi a."""
    method = emp.preferred_payment_method.value if emp.preferred_payment_method else "check"
    if method == "direct_deposit":
        return method, emp.bank_name, _last4(emp.bank_account_number)
    if method in MOBILE:
        return method, None, _last4(emp.mobile_money_number)
    return method, None, None


def _clean(method: str, bank_name: Optional[str], account: Optional[str]):
    """Valide epi nòmalize. Retounen (bank_name, account)."""
    if method == "direct_deposit":
        bank = (bank_name or "").strip()
        number = re.sub(r"[\s-]", "", account or "")
        if len(bank) < 2 or not re.fullmatch(r"[A-Za-z0-9]{4,34}", number):
            raise HTTPException(status_code=422, detail="Mete non bank lan ak nimewo kont lan.")
        return bank, number
    if method in MOBILE:
        digits = re.sub(r"[\s\-().]", "", account or "")
        if digits.startswith("+"):
            digits = digits[1:]
        if not re.fullmatch(r"\d{8,15}", digits):
            raise HTTPException(status_code=422,
                                detail="Mete yon nimewo telefòn valab pou MonCash oswa NatCash.")
        return None, digits
    return None, None


def _audit(db: Session, request: Request, user: User, action: str,
           entity_id: int, changes: str) -> None:
    db.add(AuditLog(
        organization_id=user.organization_id, user_id=user.id, action=action,
        entity_type="payment_change", entity_id=entity_id, changes=changes,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))


def _notify(db: Session, org_id: int, user_id: Optional[int], title: str, body: str, link: str):
    if user_id is not None:
        db.add(Notification(organization_id=org_id, user_id=user_id, title=title,
                            body=body, link_url=link, category="payroll"))


def _describe(method: str, bank: Optional[str], last4: Optional[str]) -> str:
    parts = [method]
    if bank:
        parts.append(bank)
    if last4:
        parts.append(f"…{last4}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# REPONS
# ---------------------------------------------------------------------------

class PaymentChangeOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_number: str
    method: str
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    current_method: str
    current_bank_name: Optional[str] = None
    current_last4: Optional[str] = None
    status: str
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None


class PaymentChangeList(BaseModel):
    total: int
    items: list[PaymentChangeOut]


def _out(db: Session, req: PaymentChangeRequest, emp: Employee) -> PaymentChangeOut:
    method, bank, last4 = _current(emp)
    decider = db.get(User, req.decided_by_id) if req.decided_by_id else None
    return PaymentChangeOut(
        id=req.id, employee_id=emp.id,
        employee_name=f"{emp.first_name} {emp.last_name}", employee_number=emp.employee_number,
        method=req.method, bank_name=req.bank_name, account_last4=_last4(req.account_number),
        current_method=method, current_bank_name=bank, current_last4=last4,
        status=req.status, created_at=req.created_at, decided_at=req.decided_at,
        decided_by=decider.full_name if decider else None, decision_note=req.decision_note,
    )


# ---------------------------------------------------------------------------
# ANPLWAYE A
# ---------------------------------------------------------------------------

class PaymentChangeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Method
    bank_name: Optional[str] = Field(default=None, max_length=150)
    account_number: Optional[str] = Field(default=None, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@router.get("/me", response_model=PaymentChangeList)
def my_requests(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    rows = db.query(PaymentChangeRequest).filter(
        PaymentChangeRequest.organization_id == org_id,
        PaymentChangeRequest.employee_id == emp.id,
    ).order_by(PaymentChangeRequest.id.desc()).limit(10).all()
    return PaymentChangeList(total=len(rows), items=[_out(db, r, emp) for r in rows])


@router.post("/me", response_model=PaymentChangeOut, status_code=status.HTTP_201_CREATED)
def create_request(payload: PaymentChangeCreate, emp: CurrentEmployee, user: CurrentUser,
                   org_id: TenantId, request: Request, db: DbSession):
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Modpas aktyèl la pa kòrèk.")

    bank, account = _clean(payload.method, payload.bank_name, payload.account_number)

    method_now, bank_now, _ = _current(emp)
    account_now = (emp.bank_account_number if method_now == "direct_deposit"
                   else emp.mobile_money_number if method_now in MOBILE else None)
    if payload.method == method_now and account == (account_now or None) \
            and (bank or None) == (bank_now or None):
        raise HTTPException(status_code=400, detail="Se deja konsa ou resevwa salè w.")

    pending = db.query(PaymentChangeRequest).filter(
        PaymentChangeRequest.organization_id == org_id,
        PaymentChangeRequest.employee_id == emp.id,
        PaymentChangeRequest.status == "pending",
    ).first()
    if pending is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ou gen yon demann k ap tann deja. Anile l anvan ou voye yon lòt.",
        )

    req = PaymentChangeRequest(
        organization_id=org_id, employee_id=emp.id, requested_by_id=user.id,
        method=payload.method, bank_name=bank, account_number=account, status="pending",
    )
    db.add(req)
    db.flush()

    _audit(db, request, user, "payment_change_request", req.id,
           f"{_describe(*_current(emp))} -> {_describe(req.method, bank, _last4(account))}")
    hr_users = db.query(User.id).filter(
        User.organization_id == org_id, User.is_active.is_(True),
        User.role.in_([UserRole.ORG_ADMIN, UserRole.HR]), User.id != user.id,
    ).all()
    for (uid,) in hr_users:
        _notify(db, org_id, uid, "Demann chanjman peman",
                f"{emp.first_name} {emp.last_name} ({emp.employee_number}) mande chanje "
                "fason li resevwa salè l.", "/payment-changes.html")
    db.commit()
    db.refresh(req)
    return _out(db, req, emp)


@router.post("/me/{request_id}/cancel", response_model=PaymentChangeOut)
def cancel_request(request_id: int, emp: CurrentEmployee, user: CurrentUser,
                   org_id: TenantId, request: Request, db: DbSession):
    req = db.query(PaymentChangeRequest).filter(
        PaymentChangeRequest.id == request_id,
        PaymentChangeRequest.organization_id == org_id,
        PaymentChangeRequest.employee_id == emp.id,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Demann chanjman an pa jwenn.")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Demann sa a deja trete.")
    req.status = "cancelled"
    req.decided_at = datetime.now(timezone.utc)
    _audit(db, request, user, "payment_change_cancel", req.id, "Anile pa anplwaye a.")
    db.commit()
    db.refresh(req)
    return _out(db, req, emp)


# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------

@router.get("", response_model=PaymentChangeList, dependencies=[Depends(require_hr)])
def list_requests(org_id: TenantId, db: DbSession,
                  status_filter: Annotated[StatusFilter, Query(alias="status")] = "pending"):
    q = (db.query(PaymentChangeRequest, Employee)
         .join(Employee, Employee.id == PaymentChangeRequest.employee_id)
         .filter(PaymentChangeRequest.organization_id == org_id,
                 Employee.organization_id == org_id))
    if status_filter != "all":
        q = q.filter(PaymentChangeRequest.status == status_filter)
    rows = q.order_by(PaymentChangeRequest.id.desc()).limit(200).all()
    return PaymentChangeList(total=len(rows), items=[_out(db, r, e) for r, e in rows])


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/{request_id}/decide", response_model=PaymentChangeOut,
             dependencies=[Depends(require_hr)])
def decide(request_id: int, payload: Decision, user: CurrentUser, org_id: TenantId,
           request: Request, db: DbSession):
    req = db.query(PaymentChangeRequest).filter(
        PaymentChangeRequest.id == request_id,
        PaymentChangeRequest.organization_id == org_id,
    ).first()
    if req is None:
        raise HTTPException(status_code=404, detail="Demann chanjman an pa jwenn.")
    emp = db.query(Employee).filter(
        Employee.id == req.employee_id, Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    if req.status != "pending":
        raise HTTPException(status_code=409, detail="Demann sa a deja trete.")
    if emp.user_id == user.id or req.requested_by_id == user.id:
        raise HTTPException(status_code=403, detail="Yon lòt moun dwe apwouve pwòp demann ou.")

    before = _describe(*_current(emp))
    note = (payload.note or "").strip() or None
    if payload.approve:
        emp.preferred_payment_method = PaymentMethod(req.method)
        if req.method == "direct_deposit":
            emp.bank_name = req.bank_name
            emp.bank_account_number = req.account_number
        elif req.method in MOBILE:
            emp.mobile_money_number = req.account_number
        req.status = "approved"
    else:
        req.status = "rejected"
    req.decided_by_id = user.id
    req.decided_at = datetime.now(timezone.utc)
    req.decision_note = note

    requested = _describe(req.method, req.bank_name, _last4(req.account_number))
    _audit(db, request, user,
           "payment_change_approve" if payload.approve else "payment_change_reject", req.id,
           f"{emp.employee_number}: {before} -> {requested}" + (f". Nòt: {note}" if note else ""))
    _notify(db, org_id, emp.user_id,
            "Chanjman peman apwouve" if payload.approve else "Chanjman peman refize",
            ("Pwochen salè w ap peye jan w te mande a." if payload.approve
             else "HR pa t aksepte chanjman an." + (f" « {note} »" if note else "")),
            "/dashboard.html#dosye")
    db.commit()
    db.refresh(req)
    return _out(db, req, emp)