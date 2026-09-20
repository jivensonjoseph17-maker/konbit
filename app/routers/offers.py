"""
Konbit — Router Pwopozisyon Travay
Chemen: backend/app/routers/offers.py

    POST   /api/offers                  Kreye yon pwopozisyon (HR)
    GET    /api/offers                  Lis pwopozisyon yo
    GET    /api/offers/{id}             Detay
    PATCH  /api/offers/{id}             Modifye yon bouyon
    POST   /api/offers/{id}/send        Voye l bay kandida a
    POST   /api/offers/{id}/respond     Aksepte oswa refize
    POST   /api/offers/{id}/hire        Konvèti kandida a an anplwaye
    DELETE /api/offers/{id}             Efase yon bouyon

SE LA REKRITMAN AN RANKONTRE JESYON ANPLWAYE A. `/hire` la pran yon
aplikasyon ki aksepte epi li kreye:
  - yon dosye Employee ak nimewo, salè, dat antre
  - yon kont User ak modpas tanporè
  - li make aplikasyon an HIRED
  - li diminye kantite pòs ki louvri nan òf la
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    Application,
    ApplicationStage,
    AuditLog,
    Currency,
    Employee,
    EmploymentStatus,
    EmploymentType,
    JobPosting,
    JobStatus,
    Offer,
    OfferStatus,
    PaymentMethod,
    User,
    UserRole,
)
from ..schemas import EmployeeOut, Message, OfferCreate, OfferOut, OfferResponse
from ..security import generate_temp_password, hash_password

logger = logging.getLogger("konbit")

router = APIRouter()


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _audit(db: Session, request: Request, user: User, action: str,
           entity_type: str, entity_id: int, changes: Optional[str] = None) -> None:
    try:
        db.add(AuditLog(
            organization_id=user.organization_id,
            user_id=user.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()


def _get_offer_or_404(db: Session, org_id: int, offer_id: int) -> Offer:
    offer = db.query(Offer).filter(
        Offer.id == offer_id,
        Offer.organization_id == org_id,
    ).first()
    if offer is None:
        raise HTTPException(status_code=404, detail="Pwopozisyon an pa jwenn.")
    return offer


def _next_employee_number(db: Session, org_id: int) -> str:
    count = db.query(Employee).filter(Employee.organization_id == org_id).count()
    num = count + 1
    while True:
        candidate = f"KB-{num:04d}"
        exists = db.query(Employee).filter(
            Employee.organization_id == org_id,
            Employee.employee_number == candidate,
        ).first()
        if exists is None:
            return candidate
        num += 1


def _is_expired(offer: Offer) -> bool:
    if offer.expires_at is None:
        return False
    exp = offer.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# KREYE AK JERE
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=OfferOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_offer(
    payload: OfferCreate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """Kreye yon pwopozisyon pou yon kandida ki nan etap antrevi oswa pi lwen."""
    app = db.query(Application).filter(
        Application.id == payload.application_id,
        Application.organization_id == org_id,
    ).first()
    if app is None:
        raise HTTPException(status_code=404, detail="Aplikasyon an pa jwenn.")

    if app.stage in (ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN):
        raise HTTPException(
            status_code=400,
            detail=f"Kandida a nan estati '{app.stage.value}'.",
        )
    if app.stage == ApplicationStage.HIRED:
        raise HTTPException(status_code=400, detail="Kandida a deja anboche.")

    active = db.query(Offer).filter(
        Offer.application_id == app.id,
        Offer.status.in_([OfferStatus.DRAFT, OfferStatus.SENT]),
    ).first()
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Gen deja yon pwopozisyon aktif (#{active.id}) pou kandida a.",
        )

    offer = Offer(
        organization_id=org_id,
        created_by_id=user.id,
        status=OfferStatus.DRAFT,
        **payload.model_dump(),
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


class OfferRow(BaseModel):
    offer: OfferOut
    candidate_name: str
    candidate_email: str
    job_title: str
    is_expired: bool


class OfferListResponse(BaseModel):
    total: int
    items: list[OfferRow]


@router.get("", response_model=OfferListResponse, dependencies=[Depends(require_hr)])
def list_offers(
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[OfferStatus], Query(alias="status")] = None,
    job_posting_id: Optional[int] = None,
):
    q = (
        db.query(Offer, Application, JobPosting)
        .join(Application, Offer.application_id == Application.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(Offer.organization_id == org_id)
    )
    if status_filter:
        q = q.filter(Offer.status == status_filter)
    if job_posting_id is not None:
        q = q.filter(Application.job_posting_id == job_posting_id)

    rows = q.order_by(Offer.created_at.desc()).all()
    return OfferListResponse(
        total=len(rows),
        items=[
            OfferRow(
                offer=OfferOut.model_validate(offer),
                candidate_name=app.full_name,
                candidate_email=app.email,
                job_title=job.title,
                is_expired=_is_expired(offer),
            )
            for offer, app, job in rows
        ],
    )


@router.get("/{offer_id}", response_model=OfferRow, dependencies=[Depends(require_hr)])
def read_offer(offer_id: int, org_id: TenantId, db: DbSession):
    offer = _get_offer_or_404(db, org_id, offer_id)
    app = db.query(Application).filter(Application.id == offer.application_id).first()
    job = db.query(JobPosting).filter(
        JobPosting.id == app.job_posting_id
    ).first() if app else None

    return OfferRow(
        offer=OfferOut.model_validate(offer),
        candidate_name=app.full_name if app else "",
        candidate_email=app.email if app else "",
        job_title=job.title if job else "",
        is_expired=_is_expired(offer),
    )


class OfferUpdate(BaseModel):
    salary: Optional[int] = Field(default=None, ge=0)
    currency: Optional[Currency] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    expires_at: Optional[datetime] = None
    document_url: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/{offer_id}", response_model=OfferOut, dependencies=[Depends(require_hr)])
def update_offer(offer_id: int, payload: OfferUpdate, org_id: TenantId, db: DbSession):
    """Sèlman pandan li bouyon — yon pwopozisyon voye pa ka chanje anba men."""
    offer = _get_offer_or_404(db, org_id, offer_id)

    if offer.status != OfferStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Pwopozisyon an nan estati '{offer.status.value}'. "
                "Sèlman yon bouyon ka modifye."
            ),
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(offer, field, value)

    db.commit()
    db.refresh(offer)
    return offer


@router.post("/{offer_id}/send", response_model=OfferOut, dependencies=[Depends(require_hr)])
def send_offer(
    offer_id: int,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Make pwopozisyon an voye. Aplikasyon an pase nan etap 'offer'.

    NÒT: sistèm lan pa voye imel pou kounye a. HR voye dokiman an
    limenm, epi li anrejistre repons kandida a ak /respond.
    """
    offer = _get_offer_or_404(db, org_id, offer_id)

    if offer.status != OfferStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Pwopozisyon an deja voye.")
    if _is_expired(offer):
        raise HTTPException(
            status_code=400,
            detail="Dat ekspirasyon an deja pase. Chanje l anvan.",
        )

    offer.status = OfferStatus.SENT

    app = db.query(Application).filter(Application.id == offer.application_id).first()
    if app and app.stage not in (ApplicationStage.HIRED, ApplicationStage.REJECTED):
        app.stage = ApplicationStage.OFFER

    db.commit()
    db.refresh(offer)
    _audit(db, request, user, "send", "offer", offer.id)
    return offer


@router.post("/{offer_id}/respond", response_model=OfferOut, dependencies=[Depends(require_hr)])
def record_response(
    offer_id: int,
    payload: OfferResponse,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """HR anrejistre repons kandida a."""
    offer = _get_offer_or_404(db, org_id, offer_id)

    if offer.status != OfferStatus.SENT:
        raise HTTPException(
            status_code=400,
            detail=f"Pwopozisyon an nan estati '{offer.status.value}'.",
        )

    if _is_expired(offer):
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Pwopozisyon an ekspire. Kreye yon nouvo.",
        )

    offer.status = OfferStatus.ACCEPTED if payload.accept else OfferStatus.DECLINED
    offer.responded_at = datetime.now(timezone.utc)
    if payload.note:
        offer.notes = f"{offer.notes or ''}\n[Repons] {payload.note}".strip()

    app = db.query(Application).filter(Application.id == offer.application_id).first()
    if app and not payload.accept:
        app.stage = ApplicationStage.WITHDRAWN

    db.commit()
    db.refresh(offer)
    _audit(db, request, user, "respond", "offer", offer.id,
           changes=f"{offer.status.value}. {payload.note or ''}")
    return offer


# ---------------------------------------------------------------------------
# ANBOCHE — KONVÈTI KANDIDA A AN ANPLWAYE
# ---------------------------------------------------------------------------

class HireRequest(BaseModel):
    """
    Enfòmasyon ki manke pou kreye dosye anplwaye a. Sa ki nan pwopozisyon
    an (salè, dat antre, tip kontra) nou pran l dirèkteman.
    """
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employee_number: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    national_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_id: Optional[int] = None

    preferred_payment_method: PaymentMethod = PaymentMethod.CHECK
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mobile_money_number: Optional[str] = None

    create_login: bool = True
    login_email: Optional[EmailStr] = None
    login_role: UserRole = UserRole.EMPLOYEE


class HireResult(BaseModel):
    employee: EmployeeOut
    login_email: Optional[str] = None
    temporary_password: Optional[str] = None
    job_closed: bool
    remaining_openings: int
    note: str


@router.post(
    "/{offer_id}/hire",
    response_model=HireResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def hire_candidate(
    offer_id: int,
    payload: HireRequest,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    """
    Konvèti yon kandida ki aksepte an anplwaye.

    Tout bagay fèt nan yon sèl tranzaksyon: si nenpòt pyès echwe,
    anyen pa ekri. San sa ou ta ka gen yon kont User san dosye Employee,
    oswa yon anplwaye ki pa ka konekte.
    """
    offer = _get_offer_or_404(db, org_id, offer_id)

    if offer.status != OfferStatus.ACCEPTED:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Pwopozisyon an nan estati '{offer.status.value}'. "
                "Kandida a dwe aksepte anvan."
            ),
        )

    app = db.query(Application).filter(Application.id == offer.application_id).first()
    if app is None:
        raise HTTPException(status_code=404, detail="Aplikasyon an pa jwenn.")
    if app.stage == ApplicationStage.HIRED:
        raise HTTPException(status_code=400, detail="Kandida a deja anboche.")

    job = db.query(JobPosting).filter(JobPosting.id == app.job_posting_id).first()

    if payload.manager_id is not None:
        mgr = db.query(Employee).filter(
            Employee.id == payload.manager_id,
            Employee.organization_id == org_id,
        ).first()
        if mgr is None:
            raise HTTPException(status_code=400, detail="Manadjè a pa jwenn.")

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
        login_email = str(payload.login_email or app.email).lower().strip()
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

    try:
        if new_user is not None:
            db.add(new_user)
            db.flush()

        emp = Employee(
            organization_id=org_id,
            user_id=new_user.id if new_user else None,
            employee_number=emp_number,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            personal_email=app.email,
            phone=payload.phone or app.phone,
            date_of_birth=payload.date_of_birth,
            national_id=payload.national_id,
            address=payload.address,
            city=payload.city,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_phone=payload.emergency_contact_phone,
            department_id=payload.department_id or (job.department_id if job else None),
            position_id=payload.position_id or (job.position_id if job else None),
            manager_id=payload.manager_id,
            employment_type=offer.employment_type,
            status=EmploymentStatus.ACTIVE,
            hire_date=offer.start_date or date.today(),
            base_salary=offer.salary,
            currency=offer.currency,
            preferred_payment_method=payload.preferred_payment_method,
            bank_name=payload.bank_name,
            bank_account_number=payload.bank_account_number,
            mobile_money_number=payload.mobile_money_number,
            is_active=True,
        )
        db.add(emp)

        app.stage = ApplicationStage.HIRED

        # Diminye pòs ki louvri yo; fèmen òf la si pa gen ankò
        job_closed = False
        remaining = 0
        if job:
            remaining = max(0, (job.openings or 1) - 1)
            job.openings = remaining
            if remaining == 0 and job.status == JobStatus.PUBLISHED:
                job.status = JobStatus.CLOSED
                job_closed = True

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Anbochaj echwe")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )

    db.refresh(emp)
    _audit(db, request, user, "hire", "employee", emp.id,
           changes=f"Depi aplikasyon #{app.id}, pwopozisyon #{offer.id}.")

    return HireResult(
        employee=EmployeeOut.model_validate(emp),
        login_email=login_email,
        temporary_password=temp_password,
        job_closed=job_closed,
        remaining_openings=remaining,
        note=(
            "Modpas tanporè a parèt yon sèl fwa. Voye l bay nouvo anplwaye a "
            "epi mande l chanje l nan premye koneksyon an."
            if temp_password else
            "Anplwaye a kreye san kont koneksyon."
        ),
    )


@router.delete("/{offer_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_offer(offer_id: int, org_id: TenantId, db: DbSession):
    offer = _get_offer_or_404(db, org_id, offer_id)
    if offer.status != OfferStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Sèlman yon bouyon ka efase.",
        )
    db.delete(offer)
    db.commit()
    return Message(detail="Pwopozisyon an efase.")