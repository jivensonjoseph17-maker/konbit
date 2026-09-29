"""
Konbit — Dosye mwen (pòtay anplwaye)
Chemen: backend/app/routers/my_profile.py

    GET   /api/profile/me     Dosye mwen: travay, kontak, fason m resevwa salè m (maske)
    PATCH /api/profile/me     Chanje kontak mwen ak moun pou rele an ijans
    GET   /api/profile/team   Manadjè mwen ak kòlèg ki gen menm manadjè a

SÈLMAN done pa moun ki konekte a. Yon anplwaye pa ka chanje salè, pozisyon,
manadjè, ni kont labank / MonCash li isit la: kont yo pase pa yon DEMANN HR
konfime (routers/payment_changes.py).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ..deps import CurrentEmployee, CurrentUser, DbSession, TenantId
from ..models import AuditLog, Department, Employee, EmploymentStatus, Position

router = APIRouter()

# Vid (pou efase l) oswa yon imel senp. Yon move imel = 422 ak mesaj tradui a.
EMAIL_PATTERN = r"^$|^\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*$"
CONTACT_FIELDS = ("phone", "personal_email", "address", "city",
                  "emergency_contact_name", "emergency_contact_phone")


def _last4(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value[-4:] if len(value) >= 4 else None


class PaymentSummary(BaseModel):
    method: str
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None


class ProfileOut(BaseModel):
    employee_id: int
    employee_number: str
    first_name: str
    last_name: str
    position_title: Optional[str] = None
    department_name: Optional[str] = None
    manager_name: Optional[str] = None
    hire_date: Optional[date] = None
    employment_type: Optional[str] = None
    login_email: Optional[str] = None
    phone: Optional[str] = None
    personal_email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    payment: PaymentSummary


def _profile(db, emp: Employee, login_email: Optional[str]) -> ProfileOut:
    position = db.get(Position, emp.position_id) if emp.position_id else None
    dept = db.get(Department, emp.department_id) if emp.department_id else None
    manager = db.get(Employee, emp.manager_id) if emp.manager_id else None

    method = emp.preferred_payment_method.value if emp.preferred_payment_method else "check"
    if method == "direct_deposit":
        payment = PaymentSummary(method=method, bank_name=emp.bank_name,
                                 account_last4=_last4(emp.bank_account_number))
    elif method in ("moncash", "natcash"):
        payment = PaymentSummary(method=method, account_last4=_last4(emp.mobile_money_number))
    else:
        payment = PaymentSummary(method=method)

    return ProfileOut(
        employee_id=emp.id, employee_number=emp.employee_number,
        first_name=emp.first_name, last_name=emp.last_name,
        position_title=position.title if position else None,
        department_name=dept.name if dept else None,
        manager_name=f"{manager.first_name} {manager.last_name}" if manager else None,
        hire_date=emp.hire_date,
        employment_type=emp.employment_type.value if emp.employment_type else None,
        login_email=login_email,
        phone=emp.phone, personal_email=emp.personal_email, address=emp.address, city=emp.city,
        emergency_contact_name=emp.emergency_contact_name,
        emergency_contact_phone=emp.emergency_contact_phone,
        payment=payment,
    )


@router.get("/me", response_model=ProfileOut)
def read_profile(emp: CurrentEmployee, user: CurrentUser, db: DbSession):
    return _profile(db, emp, user.email)


class ContactUpdate(BaseModel):
    # "forbid": yon chan ki pa nan lis la (salè, manadjè, kont...) = 422, pa silans.
    model_config = ConfigDict(extra="forbid")
    phone: Optional[str] = Field(default=None, max_length=50)
    personal_email: Optional[str] = Field(default=None, max_length=255, pattern=EMAIL_PATTERN)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    emergency_contact_name: Optional[str] = Field(default=None, max_length=200)
    emergency_contact_phone: Optional[str] = Field(default=None, max_length=50)


@router.patch("/me", response_model=ProfileOut)
def update_profile(payload: ContactUpdate, emp: CurrentEmployee, user: CurrentUser,
                   org_id: TenantId, request: Request, db: DbSession):
    data = payload.model_dump(exclude_unset=True)
    changed = []
    for field in CONTACT_FIELDS:
        if field not in data:
            continue
        value = (data[field] or "").strip() or None
        if getattr(emp, field) != value:
            setattr(emp, field, value)
            changed.append(field)

    if changed:
        db.add(AuditLog(
            organization_id=org_id, user_id=user.id, action="update", entity_type="employee",
            entity_id=emp.id, changes=f"Dosye mwen: {', '.join(changed)}",
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
        db.refresh(emp)
    return _profile(db, emp, user.email)


# ---------------------------------------------------------------------------
# KÒLÈG MWEN YO
# ---------------------------------------------------------------------------

class Person(BaseModel):
    employee_id: int
    name: str
    employee_number: str
    position_title: Optional[str] = None


class TeamOut(BaseModel):
    manager: Optional[Person] = None
    colleagues: list[Person]


def _person(db, e: Employee) -> Person:
    position = db.get(Position, e.position_id) if e.position_id else None
    return Person(employee_id=e.id, name=f"{e.first_name} {e.last_name}",
                  employee_number=e.employee_number,
                  position_title=position.title if position else None)


@router.get("/team", response_model=TeamOut)
def my_team(emp: CurrentEmployee, org_id: TenantId, db: DbSession):
    """Non, nimewo ak pozisyon sèlman — pa kontak, pa salè."""
    manager = db.get(Employee, emp.manager_id) if emp.manager_id else None
    if manager is not None and manager.organization_id != org_id:
        manager = None
    colleagues = []
    if emp.manager_id:
        colleagues = db.query(Employee).filter(
            Employee.organization_id == org_id,
            Employee.manager_id == emp.manager_id,
            Employee.id != emp.id,
            Employee.is_active.is_(True),
            Employee.status != EmploymentStatus.TERMINATED,
        ).order_by(Employee.first_name, Employee.last_name).limit(100).all()
    return TeamOut(
        manager=_person(db, manager) if manager else None,
        colleagues=[_person(db, c) for c in colleagues],
    )