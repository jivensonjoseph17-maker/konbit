"""
Konbit — Espas kandida (paj karyè)
Chemen: backend/app/routers/candidate.py

    POST /api/candidate/signup                        Kreye yon kont kandida (piblik)
    GET  /api/candidate/applications                  Aplikasyon mwen yo (tout biznis)
    POST /api/candidate/applications/{id}/withdraw    Retire aplikasyon mwen
    POST /api/candidate/offers/{id}/respond           Aksepte / refize yon pwopozisyon

KONT KANDIDA: User.role = APPLICANT, organization_id = NULL. Li pa fè pati
okenn biznis: get_tenant refize l (403) sou tout endpoint biznis yo.

IMEL VERIFYE OBLIGATWA: aplikasyon yo konekte ak kont lan pa IMEL. San
verifikasyon, nenpòt moun ta ka kreye yon kont ak imel yon lòt moun epi
li aplikasyon li yo. Se poutèt sa chak endpoint (eksepte signup) mande
email_verified.

ENSKRIPSYON: repons lan TOUJOU menm jan an. Si imel la deja gen yon kont,
se MÈT imel la ki resevwa yon imel ("ou deja gen yon kont") — repons API a
pa revele anyen.

SA KANDIDA A PA JANM WÈ: nòt entèn, evalyasyon (rating), rezon refi a,
repons sansib yo, non moun ki fè antrevi a. Repons yo konstwi chan pa
chan (menm prensip ak jobs._to_public).
"""

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import CurrentUser, DbSession
from ..email_texts import account_exists_text
from ..i18n import requested_language
from ..legal import require_terms, stamp_terms
from ..login_guard import SIGNUP, client_ip, record_attempt, signup_blocked
from ..mailer import send_email
from ..models import (
    Application,
    ApplicationStage,
    AuditLog,
    Interview,
    JobPosting,
    Notification,
    Offer,
    OfferStatus,
    Organization,
    User,
    UserRole,
)
from ..schemas import Message
from ..security import DUMMY_HASH, hash_password, validate_password_strength, verify_password
from .auth import send_verification
from .org_logo import logo_url_for

logger = logging.getLogger("konbit")

router = APIRouter()

SIGNUP_REPLY = "Nou voye yon imel ba ou. Louvri lyen ki ladan l pou w aktive kont ou."
TOO_MANY_SIGNUPS = "Twòp enskripsyon soti nan menm koneksyon an. Eseye ankò pita."

# Etap entèn → sa kandida a wè. "rejected" vin "closed" (pa retni), san rezon.
PUBLIC_STATUS = {
    ApplicationStage.RECEIVED: "received",
    ApplicationStage.SCREENING: "review",
    ApplicationStage.INTERVIEW: "interview",
    ApplicationStage.OFFER: "offer",
    ApplicationStage.HIRED: "hired",
    ApplicationStage.REJECTED: "closed",
    ApplicationStage.WITHDRAWN: "withdrawn",
}
WITHDRAWABLE = {
    ApplicationStage.RECEIVED, ApplicationStage.SCREENING,
    ApplicationStage.INTERVIEW, ApplicationStage.OFFER,
}


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _require_candidate(user: CurrentUser) -> User:
    if user.role != UserRole.APPLICANT:
        raise HTTPException(status_code=403, detail="Espas sa a se pou kandida sèlman.")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Verifye imel ou anvan. Gade bwat imel ou.")
    return user


Candidate = Annotated[User, Depends(_require_candidate)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _is_http(url: Optional[str]) -> bool:
    return bool(url) and url.lower().startswith(("https://", "http://"))


def _mine(db: Session, user: User):
    """Aplikasyon kandida a: sa ki deja konekte ak kont lan, oswa ak menm imel la."""
    return db.query(Application).filter(or_(
        Application.applicant_user_id == user.id,
        func.lower(Application.email) == user.email,
    ))


def _owned_or_404(db: Session, user: User, application_id: int) -> Application:
    app = _mine(db, user).filter(Application.id == application_id).first()
    if app is None:
        raise HTTPException(status_code=404)
    return app


def _audit(db: Session, request: Request, user: User, org_id: int,
           action: str, entity_id: int, changes: Optional[str] = None) -> None:
    """Jounal odit BIZNIS la: HR wè sa kandida a fè sou aplikasyon an."""
    try:
        db.add(AuditLog(
            organization_id=org_id, user_id=user.id, action=action,
            entity_type="application", entity_id=entity_id, changes=changes,
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Jounal odit echwe", exc_info=True)


def _notify_hr(db: Session, org_id: int, user_id: Optional[int], title: str, body: str) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id, user_id=user_id, title=title, body=body,
            link_url="jobs.html", category="hiring",
        ))
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# SA KANDIDA A WÈ
# ---------------------------------------------------------------------------

class CandidateInterview(BaseModel):
    scheduled_at: datetime
    duration_minutes: int
    location: Optional[str] = None
    round_number: int
    completed: bool


class CandidateOffer(BaseModel):
    id: int
    status: str                      # sent, accepted, declined, expired
    salary: int                      # an santim
    currency: str
    employment_type: str
    start_date: Optional[date] = None
    expires_at: Optional[datetime] = None
    document_url: Optional[str] = None
    can_respond: bool


class CandidateApplication(BaseModel):
    id: int
    company_name: str
    company_logo: Optional[str] = None
    org_slug: str
    job_title: str
    job_slug: Optional[str] = None
    status: str                      # gade PUBLIC_STATUS
    submitted_at: datetime
    interviews: list[CandidateInterview] = []
    offer: Optional[CandidateOffer] = None
    can_withdraw: bool


class CandidateApplicationList(BaseModel):
    total: int
    items: list[CandidateApplication]


def _offer_view(offer: Optional[Offer]) -> Optional[CandidateOffer]:
    if offer is None:
        return None
    expired = (
        offer.status == OfferStatus.SENT
        and offer.expires_at is not None
        and _aware(offer.expires_at) <= _now()
    )
    return CandidateOffer(
        id=offer.id,
        status="expired" if expired else offer.status.value,
        salary=offer.salary,
        currency=offer.currency.value if offer.currency else "HTG",
        employment_type=offer.employment_type.value if offer.employment_type else "full_time",
        start_date=offer.start_date,
        expires_at=offer.expires_at,
        document_url=offer.document_url if _is_http(offer.document_url) else None,
        can_respond=offer.status == OfferStatus.SENT and not expired,
    )


def _view(db: Session, app: Application) -> CandidateApplication:
    job = db.query(JobPosting).filter(JobPosting.id == app.job_posting_id).first()
    org = db.query(Organization).filter(Organization.id == app.organization_id).first()
    interviews = db.query(Interview).filter(
        Interview.application_id == app.id
    ).order_by(Interview.scheduled_at).all()
    offer = db.query(Offer).filter(
        Offer.application_id == app.id,
        Offer.status != OfferStatus.DRAFT,
    ).order_by(Offer.created_at.desc(), Offer.id.desc()).first()

    return CandidateApplication(
        id=app.id,
        company_name=org.name if org else "",
        company_logo=logo_url_for(db, org) if org else None,
        org_slug=org.slug if org else "",
        job_title=job.title if job else "",
        job_slug=job.slug if job else None,
        status=PUBLIC_STATUS.get(app.stage, "received"),
        submitted_at=app.created_at,
        interviews=[
            CandidateInterview(
                scheduled_at=iv.scheduled_at,
                duration_minutes=iv.duration_minutes or 45,
                location=iv.location,
                round_number=iv.round_number or 1,
                completed=bool(iv.completed),
            )
            for iv in interviews
        ],
        offer=_offer_view(offer),
        can_withdraw=app.stage in WITHDRAWABLE,
    )


# ---------------------------------------------------------------------------
# ENSKRIPSYON — PIBLIK
# ---------------------------------------------------------------------------

class CandidateSignup(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    accept_terms: bool = False          # app/legal.py — obligatwa


@router.post("/signup", response_model=Message)
def candidate_signup(
    payload: CandidateSignup,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
):
    ip = client_ip(request)
    if signup_blocked(db, ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=TOO_MANY_SIGNUPS)

    problems = validate_password_strength(payload.password)
    if problems:
        raise HTTPException(status_code=422, detail=problems)

    require_terms(payload.accept_terms)
    record_attempt(db, SIGNUP, ip, payload.email, success=False)
    email = payload.email.lower().strip()
    language = requested_language(request.headers.get("accept-language"))

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        # Menm travay bcrypt ak yon nouvo kont: tan repons lan pa revele anyen.
        verify_password(payload.password, DUMMY_HASH)
        subject, text = account_exists_text(
            existing.preferred_language or language, existing.full_name,
            f"{settings.frontend_url.rstrip('/')}/login.html#bliye",
        )
        background.add_task(send_email, email, subject, text)
        return Message(detail=SIGNUP_REPLY)

    user = User(
        organization_id=None,
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.APPLICANT,
        preferred_language=language,
        is_active=True,
        email_verified=False,
    )
    stamp_terms(user, payload.accept_terms)
    db.add(user)
    db.commit()
    db.refresh(user)
    send_verification(db, user, background)
    return Message(detail=SIGNUP_REPLY)


# ---------------------------------------------------------------------------
# APLIKASYON MWEN YO
# ---------------------------------------------------------------------------

@router.get("/applications", response_model=CandidateApplicationList)
def my_applications(user: Candidate, db: DbSession):
    """
    Tout aplikasyon kandida a, nan tout biznis. Aplikasyon ki te voye ak
    menm imel la (anvan kont lan te egziste) konekte ak kont lan isit.
    """
    apps = _mine(db, user).order_by(Application.created_at.desc(), Application.id.desc()).all()

    linked = False
    for app in apps:
        if app.applicant_user_id is None:
            app.applicant_user_id = user.id
            linked = True
    if linked:
        db.commit()

    return CandidateApplicationList(total=len(apps), items=[_view(db, a) for a in apps])


@router.post("/applications/{application_id}/withdraw", response_model=CandidateApplication)
def withdraw_application(application_id: int, user: Candidate, request: Request, db: DbSession):
    app = _owned_or_404(db, user, application_id)
    if app.stage not in WITHDRAWABLE:
        raise HTTPException(status_code=400, detail="Ou pa ka retire aplikasyon sa a ankò.")

    app.stage = ApplicationStage.WITHDRAWN
    # Yon pwopozisyon ki t ap tann repons: kandida a refize l an menm tan.
    for offer in db.query(Offer).filter(
        Offer.application_id == app.id, Offer.status == OfferStatus.SENT,
    ).all():
        offer.status = OfferStatus.DECLINED
        offer.responded_at = _now()
    db.commit()

    job = db.query(JobPosting).filter(JobPosting.id == app.job_posting_id).first()
    _notify_hr(db, app.organization_id, job.created_by_id if job else None,
               title="Kandida a retire aplikasyon l",
               body=f"{app.full_name} retire aplikasyon l pou '{job.title if job else ''}'.")
    _audit(db, request, user, app.organization_id, "candidate_withdraw", app.id)
    return _view(db, app)


class CandidateOfferResponse(BaseModel):
    accept: bool
    note: Optional[str] = Field(default=None, max_length=1000)


@router.post("/offers/{offer_id}/respond", response_model=CandidateApplication)
def respond_to_offer(
    offer_id: int,
    payload: CandidateOfferResponse,
    user: Candidate,
    request: Request,
    db: DbSession,
):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if offer is None:
        raise HTTPException(status_code=404)
    app = _owned_or_404(db, user, offer.application_id)   # 404 si se pa pa l

    if offer.status != OfferStatus.SENT:
        raise HTTPException(status_code=400, detail="Pwopozisyon sa a pa ka reponn ankò.")
    if offer.expires_at is not None and _aware(offer.expires_at) <= _now():
        offer.status = OfferStatus.EXPIRED
        db.commit()
        raise HTTPException(status_code=400, detail="Pwopozisyon sa a ekspire.")

    offer.status = OfferStatus.ACCEPTED if payload.accept else OfferStatus.DECLINED
    offer.responded_at = _now()
    note = (payload.note or "").strip()
    if note:
        offer.notes = f"{offer.notes or ''}\n[Repons kandida] {note}".strip()
    if not payload.accept:
        app.stage = ApplicationStage.WITHDRAWN
    db.commit()

    job = db.query(JobPosting).filter(JobPosting.id == app.job_posting_id).first()
    _notify_hr(
        db, app.organization_id, offer.created_by_id,
        title="Kandida a aksepte pwopozisyon an" if payload.accept else "Kandida a refize pwopozisyon an",
        body=f"{app.full_name} — '{job.title if job else ''}'."
             + (f" « {note} »" if note else ""),
    )
    _audit(db, request, user, app.organization_id,
           "candidate_accept_offer" if payload.accept else "candidate_decline_offer",
           app.id, changes=f"Pwopozisyon #{offer.id}. {note}".strip())
    return _view(db, app)