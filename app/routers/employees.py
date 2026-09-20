"""
Konbit — Router Anplwaye
Chemen: backend/app/routers/employees.py

Endpoint yo:
    GET    /api/employees               Lis anplwaye (filtre ak rechèch)
    POST   /api/employees               Kreye yon anplwaye (+ kont koneksyon)
    GET    /api/employees/me            Pwòp dosye mwen
    GET    /api/employees/{id}          Yon dosye anplwaye
    PATCH  /api/employees/{id}          Modifye
    POST   /api/employees/{id}/terminate    Mete l deyò
    POST   /api/employees/{id}/reactivate   Remete l
    GET    /api/employees/{id}/sensitive    NIF + nimewo kont (HR sèlman, odite)
    POST   /api/employees/{id}/reset-password  Jenere yon modpas tanporè

RÈG: chak rekèt filtre sou `organization_id` ki soti nan token an.
"""

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..deps import (
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    is_in_management_chain,
    require_hr,
)
from ..models import (
    AuditLog,
    Department,
    Employee,
    EmploymentStatus,
    Organization,
    Position,
    User,
    UserRole,
)
from ..schemas import (
    EmployeeBrief,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    Message,
    TerminationRequest,
)
from ..security import generate_temp_password, hash_password

logger = logging.getLogger("konbit")

router = APIRouter()


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
            entity_type="employee",
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _next_employee_number(db: Session, org_id: int) -> str:
    """
    Jenere pwochen nimewo a: KB-0001, KB-0002...
    Nou konte anplwaye ki egziste yo epi nou monte jouk nou jwenn youn ki lib,
    paske si yon dosye efase, konte a ka bay yon nimewo ki deja pran.
    """
    count = db.query(Employee).filter(Employee.organization_id == org_id).count()
    candidate_num = count + 1
    while True:
        candidate = f"KB-{candidate_num:04d}"
        exists = db.query(Employee).filter(
            Employee.organization_id == org_id,
            Employee.employee_number == candidate,
        ).first()
        if exists is None:
            return candidate
        candidate_num += 1


def _get_employee_or_404(db: Session, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,      # <-- izolasyon
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    return emp


def _would_create_cycle(db: Session, org_id: int, employee_id: int,
                        new_manager_id: int, max_depth: int = 20) -> bool:
    """
    Anpeche A → B → A. San verifikasyon sa a, òganigram lan ap tounen
    yon bouk enfini epi sèvè a ap bloke.
    """
    if employee_id == new_manager_id:
        return True
    current_id, depth = new_manager_id, 0
    while current_id is not None and depth < max_depth:
        if current_id == employee_id:
            return True
        parent = db.query(Employee.manager_id).filter(
            Employee.id == current_id,
            Employee.organization_id == org_id,
        ).first()
        current_id = parent[0] if parent else None
        depth += 1
    return False


def _validate_refs(db: Session, org_id: int, department_id: Optional[int],
                   position_id: Optional[int], manager_id: Optional[int]) -> None:
    """Verifye ke depatman/pozisyon/manadjè yo se pou MENM biznis lan."""
    if department_id is not None:
        ok = db.query(Department).filter(
            Department.id == department_id,
            Department.organization_id == org_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Depatman an pa jwenn.")

    if position_id is not None:
        ok = db.query(Position).filter(
            Position.id == position_id,
            Position.organization_id == org_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Pozisyon an pa jwenn.")

    if manager_id is not None:
        ok = db.query(Employee).filter(
            Employee.id == manager_id,
            Employee.organization_id == org_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Manadjè a pa jwenn.")


# ---------------------------------------------------------------------------
# LIS
# ---------------------------------------------------------------------------

class EmployeeListResponse(BaseModel):
    total: int
    page: int
    size: int
    items: list[EmployeeBrief]


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    q: Annotated[Optional[str], Query(description="Rechèch sou non oswa nimewo")] = None,
    department_id: Optional[int] = None,
    status_filter: Annotated[Optional[EmploymentStatus], Query(alias="status")] = None,
    manager_id: Optional[int] = None,
    include_inactive: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """
    HR ak admin wè tout moun. Yon manadjè wè sèlman ekip li.
    Yon anplwaye regilye wè yon lis debaz (non ak pozisyon), pa done sansib.
    """
    query = db.query(Employee).filter(Employee.organization_id == org_id)

    if not include_inactive:
        query = query.filter(Employee.is_active.is_(True))

    # Restriksyon pou manadjè: sèlman moun ki anba l
    if user.role == UserRole.MANAGER:
        viewer = db.query(Employee).filter(Employee.user_id == user.id).first()
        if viewer is None:
            raise HTTPException(status_code=403, detail="Kont ou a pa lye ak yon dosye anplwaye.")
        subordinate_ids = _collect_subordinate_ids(db, org_id, viewer.id)
        subordinate_ids.add(viewer.id)
        query = query.filter(Employee.id.in_(subordinate_ids))

    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(
            Employee.first_name.ilike(pattern),
            Employee.last_name.ilike(pattern),
            Employee.employee_number.ilike(pattern),
        ))

    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if status_filter is not None:
        query = query.filter(Employee.status == status_filter)
    if manager_id is not None:
        query = query.filter(Employee.manager_id == manager_id)

    total = query.count()
    items = (
        query.order_by(Employee.last_name, Employee.first_name)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return EmployeeListResponse(
        total=total,
        page=page,
        size=size,
        items=[EmployeeBrief.model_validate(e) for e in items],
    )


def _collect_subordinate_ids(db: Session, org_id: int, manager_id: int,
                             max_depth: int = 10) -> set[int]:
    """Tout moun ki anba yon manadjè, sou tout nivo."""
    collected: set[int] = set()
    frontier = [manager_id]
    depth = 0
    while frontier and depth < max_depth:
        rows = db.query(Employee.id).filter(
            Employee.organization_id == org_id,
            Employee.manager_id.in_(frontier),
        ).all()
        next_frontier = [r[0] for r in rows if r[0] not in collected]
        collected.update(next_frontier)
        frontier = next_frontier
        depth += 1
    return collected


# ---------------------------------------------------------------------------
# PWÒP DOSYE MWEN
# ---------------------------------------------------------------------------

@router.get("/me", response_model=EmployeeOut)
def read_my_record(user: CurrentUser, org_id: TenantId, db: DbSession):
    emp = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(
            status_code=404,
            detail="Kont ou a pa lye ak yon dosye anplwaye.",
        )
    return emp


# ---------------------------------------------------------------------------
# KREYE
# ---------------------------------------------------------------------------

class EmployeeCreated(BaseModel):
    employee: EmployeeOut
    login_email: Optional[str] = None
    temporary_password: Optional[str] = None
    note: Optional[str] = None


@router.post(
    "",
    response_model=EmployeeCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_employee(
    payload: EmployeeCreate,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Kreye dosye anplwaye a, epi opsyonèlman yon kont koneksyon.
    Modpas tanporè a retounen YON SÈL FWA — li pa estoke an klè okenn kote.
    """
    _validate_refs(db, org_id, payload.department_id, payload.position_id, payload.manager_id)

    emp_number = (payload.employee_number or "").strip() or _next_employee_number(db, org_id)
    if db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.employee_number == emp_number,
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Nimewo '{emp_number}' la deja pran.",
        )

    login_email = None
    temp_password = None
    new_user = None

    if payload.create_login:
        login_email = str(payload.login_email or payload.personal_email).lower().strip()
        if db.query(User).filter(User.email == login_email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Yon kont ak imel '{login_email}' deja egziste.",
            )
        temp_password = generate_temp_password()
        new_user = User(
            organization_id=org_id,
            email=login_email,
            hashed_password=hash_password(temp_password),
            full_name=f"{payload.first_name.strip()} {payload.last_name.strip()}",
            role=payload.login_role,
            is_active=True,
            email_verified=False,
        )

    data = payload.model_dump(exclude={
        "create_login", "login_email", "login_role", "employee_number",
    })

    try:
        if new_user is not None:
            db.add(new_user)
            db.flush()

        emp = Employee(
            organization_id=org_id,
            employee_number=emp_number,
            user_id=new_user.id if new_user else None,
            status=EmploymentStatus.ACTIVE,
            is_active=True,
            **data,
        )
        db.add(emp)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Kreyasyon anplwaye echwe")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    db.refresh(emp)
    _audit(db, request, user, "create", emp.id)

    return EmployeeCreated(
        employee=EmployeeOut.model_validate(emp),
        login_email=login_email,
        temporary_password=temp_password,
        note=(
            "Modpas tanporè a parèt yon sèl fwa. Voye l bay anplwaye a epi "
            "mande l chanje l nan premye koneksyon an."
            if temp_password else None
        ),
    )


# ---------------------------------------------------------------------------
# LI YON DOSYE
# ---------------------------------------------------------------------------

@router.get("/{employee_id}", response_model=EmployeeOut)
def read_employee(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    emp = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, emp, db)
    return emp


# ---------------------------------------------------------------------------
# MODIFYE
# ---------------------------------------------------------------------------

@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    HR ak admin ka chanje tout bagay.
    Yon anplwaye ka chanje sèlman kontak pèsonèl li — pa salè, pa manadjè.
    """
    emp = _get_employee_or_404(db, org_id, employee_id)
    data = payload.model_dump(exclude_unset=True)

    is_hr = user.role in (UserRole.ORG_ADMIN, UserRole.HR, UserRole.SUPER_ADMIN)

    if not is_hr:
        # Anplwaye a ka chanje pwòp kontak li sèlman
        if emp.user_id != user.id:
            raise HTTPException(status_code=403, detail="Ou pa gen dwa modifye dosye sa a.")
        allowed = {
            "phone", "personal_email", "address", "city", "photo_url",
            "emergency_contact_name", "emergency_contact_phone",
            "mobile_money_number",
        }
        forbidden = set(data) - allowed
        if forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Ou pa ka chanje: {', '.join(sorted(forbidden))}.",
            )

    _validate_refs(
        db, org_id,
        data.get("department_id"),
        data.get("position_id"),
        data.get("manager_id"),
    )

    if "manager_id" in data and data["manager_id"] is not None:
        if _would_create_cycle(db, org_id, emp.id, data["manager_id"]):
            raise HTTPException(
                status_code=400,
                detail="Chanjman sa a ap kreye yon bouk nan òganigram lan.",
            )

    changed = []
    for field, value in data.items():
        old = getattr(emp, field, None)
        if old != value:
            changed.append(field)
            setattr(emp, field, value)

    if not changed:
        return emp

    db.commit()
    db.refresh(emp)
    _audit(db, request, user, "update", emp.id, changes=", ".join(changed))
    return emp


# ---------------------------------------------------------------------------
# METE DEYÒ / REMETE
# ---------------------------------------------------------------------------

@router.post(
    "/{employee_id}/terminate",
    response_model=EmployeeOut,
    dependencies=[Depends(require_hr)],
)
def terminate_employee(
    employee_id: int,
    payload: TerminationRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Nou PA efase dosye a — se yon dokiman legal. Nou make l TERMINATED.
    Moun ki te anba l yo pase anba manadjè li a, pou òganigram lan pa kase.
    """
    emp = _get_employee_or_404(db, org_id, employee_id)

    if emp.status == EmploymentStatus.TERMINATED:
        raise HTTPException(status_code=400, detail="Anplwaye a deja pa nan biznis la.")

    emp.status = EmploymentStatus.TERMINATED
    emp.termination_date = payload.termination_date
    emp.termination_reason = payload.reason
    emp.is_active = False

    # Moun ki te anba l yo monte yon nivo
    reports = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.manager_id == emp.id,
    ).all()
    for r in reports:
        r.manager_id = emp.manager_id

    if payload.deactivate_login and emp.user_id:
        login = db.query(User).filter(User.id == emp.user_id).first()
        if login:
            login.is_active = False

    db.commit()
    db.refresh(emp)
    _audit(db, request, user, "terminate", emp.id, changes=payload.reason)
    return emp


@router.post(
    "/{employee_id}/reactivate",
    response_model=EmployeeOut,
    dependencies=[Depends(require_hr)],
)
def reactivate_employee(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    emp = _get_employee_or_404(db, org_id, employee_id)
    emp.status = EmploymentStatus.ACTIVE
    emp.termination_date = None
    emp.termination_reason = None
    emp.is_active = True

    if emp.user_id:
        login = db.query(User).filter(User.id == emp.user_id).first()
        if login:
            login.is_active = True
            login.failed_login_count = 0

    db.commit()
    db.refresh(emp)
    _audit(db, request, user, "reactivate", emp.id)
    return emp


# ---------------------------------------------------------------------------
# DONE SANSIB
# ---------------------------------------------------------------------------

class SensitiveData(BaseModel):
    employee_id: int
    national_id: Optional[str] = None
    bank_account_number: Optional[str] = None
    date_of_birth: Optional[str] = None


@router.get(
    "/{employee_id}/sensitive",
    response_model=SensitiveData,
    dependencies=[Depends(require_hr)],
)
def read_sensitive(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    NIF ak nimewo kont labank. Chak apèl ekri nan jounal odit la —
    se konsa ou ka reponn 'kiyès ki gade nimewo kont Mari a?'
    """
    emp = _get_employee_or_404(db, org_id, employee_id)
    _audit(db, request, user, "view_sensitive", emp.id)
    return SensitiveData(
        employee_id=emp.id,
        national_id=emp.national_id,
        bank_account_number=emp.bank_account_number,
        date_of_birth=emp.date_of_birth.isoformat() if emp.date_of_birth else None,
    )


# ---------------------------------------------------------------------------
# MODPAS TANPORÈ
# ---------------------------------------------------------------------------

class TempPasswordResponse(BaseModel):
    login_email: str
    temporary_password: str
    note: str


@router.post(
    "/{employee_id}/reset-password",
    response_model=TempPasswordResponse,
    dependencies=[Depends(require_hr)],
)
def reset_employee_password(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    emp = _get_employee_or_404(db, org_id, employee_id)
    if not emp.user_id:
        raise HTTPException(status_code=400, detail="Anplwaye a pa gen kont koneksyon.")

    login = db.query(User).filter(User.id == emp.user_id).first()
    if login is None:
        raise HTTPException(status_code=404, detail="Kont koneksyon an pa jwenn.")

    temp = generate_temp_password()
    login.hashed_password = hash_password(temp)
    login.failed_login_count = 0
    db.commit()

    _audit(db, request, user, "reset_password", emp.id)
    return TempPasswordResponse(
        login_email=login.email,
        temporary_password=temp,
        note="Modpas sa a parèt yon sèl fwa. Mande anplwaye a chanje l touswit.",
    )