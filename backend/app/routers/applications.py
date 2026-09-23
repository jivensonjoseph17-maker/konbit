"""
Konbit — Router Aplikasyon ak Antrevi
Chemen: backend/app/routers/applications.py

PIBLIK (san otantifikasyon):
    POST /api/applications/public/{org_slug}/{job_slug}   Aplike pou yon travay

ENTÈN (HR / manadjè):
    GET    /api/applications                      Lis ak filtè
    GET    /api/applications/pipeline/{job_id}    Kandida yo gwoupe pa etap
    GET    /api/applications/{id}                 Detay ak antrevi yo
    PATCH  /api/applications/{id}                 Chanje etap, nòt, kòmantè
    POST   /api/applications/{id}/reject          Refize ak yon rezon

    POST   /api/applications/{id}/interviews      Planifye yon antrevi
    PATCH  /api/applications/interviews/{id}      Rezilta antrevi a
    GET    /api/applications/interviews/upcoming  Antrevi ki ap vini

ETAP YO: received → screening → interview → offer → hired
         (rejected ak withdrawn ka rive nenpòt moman)

DAT: `scheduled_at` dwe gen yon fizo orè (UtcDatetime). Li sere an UTC,
epi nou konvèti l nan lè biznis la sèlman pou sa moun li (notifikasyon).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_hr, require_manager
from ..models import (
    Application,
    ApplicationStage,
    Employee,
    Interview,
    JobPosting,
    JobStatus,
    Notification,
    Organization,
)
from ..schemas import (
    ApplicationOut,
    ApplicationUpdate,
    InterviewCreate,
    InterviewOut,
    Message,
    UtcDatetime,
)
from ..timezone_utils import get_org_timezone

logger = logging.getLogger("konbit")

router = APIRouter()

# Etap ki ka avanse nan ki lòt etap. Nou refize so — yon moun pa ka pase
# de "resevwa" dirèk a "anboche" san pesonn pa wè l.
ALLOWED_TRANSITIONS: dict[ApplicationStage, set[ApplicationStage]] = {
    ApplicationStage.RECEIVED: {
        ApplicationStage.SCREENING, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    },
    ApplicationStage.SCREENING: {
        ApplicationStage.INTERVIEW, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    },
    ApplicationStage.INTERVIEW: {
        ApplicationStage.OFFER, ApplicationStage.SCREENING,
        ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN,
    },
    ApplicationStage.OFFER: {
        ApplicationStage.HIRED, ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    },
    ApplicationStage.HIRED: set(),
    ApplicationStage.REJECTED: {ApplicationStage.SCREENING},   # rekonsidere
    ApplicationStage.WITHDRAWN: {ApplicationStage.SCREENING},
}


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _notify(db: Session, org_id: int, user_id: Optional[int],
            title: str, body: str, link: Optional[str] = None) -> None:
    if user_id is None:
        return
    try:
        db.add(Notification(
            organization_id=org_id, user_id=user_id,
            title=title, body=body, link_url=link, category="hiring",
        ))
        db.commit()
    except Exception:
        db.rollback()


def _get_application_or_404(db: Session, org_id: int, app_id: int) -> Application:
    app = db.query(Application).filter(
        Application.id == app_id,
        Application.organization_id == org_id,
    ).first()
    if app is None:
        raise HTTPException(status_code=404, detail="Aplikasyon an pa jwenn.")
    return app


def _get_interview_or_404(db: Session, org_id: int, interview_id: int) -> Interview:
    iv = db.query(Interview).filter(
        Interview.id == interview_id,
        Interview.organization_id == org_id,
    ).first()
    if iv is None:
        raise HTTPException(status_code=404, detail="Antrevi a pa jwenn.")
    return iv


def _format_local(db: Session, org_id: int, when_utc: datetime) -> str:
    """
    Montre yon lè UTC nan lè biznis la, pou moun li l.

    Nou resevwa `when_utc` dirèkteman nan payload la (ki gen fizo orè),
    PA nan objè a apre db.refresh(): SQLite retounen l san fizo orè, epi
    .astimezone() ta konsidere l kòm lè òdinatè sèvè a — sa ta bay yon fo lè.
    """
    return f"{when_utc.astimezone(get_org_timezone(db, org_id)):%d/%m/%Y %H:%M}"


# ---------------------------------------------------------------------------
# APLIKE — PIBLIK
# ---------------------------------------------------------------------------

class PublicApplicationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    source: Optional[str] = None


class ApplicationReceipt(BaseModel):
    application_id: int
    job_title: str
    company_name: str
    message: str


@router.post(
    "/public/{org_slug}/{job_slug}",
    response_model=ApplicationReceipt,
    status_code=status.HTTP_201_CREATED,
    tags=["Piblik"],
)
def apply_public(
    org_slug: str,
    job_slug: str,
    payload: PublicApplicationCreate,
    db: DbSession,
):
    """
    Aplike pou yon travay depi paj karyè a. Pa gen otantifikasyon.

    Repons lan pa bay okenn enfòmasyon entèn — jis yon resi. Se enpòtan:
    si nou te di "ou deja aplike", nenpòt moun ta ka teste yon imel pou
    konnen si yon moun aplike nan yon biznis.
    """
    org = db.query(Organization).filter(
        Organization.slug == org_slug.lower().strip(),
        Organization.is_active.is_(True),
    ).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Biznis la pa jwenn.")

    job = db.query(JobPosting).filter(
        JobPosting.organization_id == org.id,
        JobPosting.slug == job_slug.lower().strip(),
        JobPosting.status == JobStatus.PUBLISHED,
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Òf travay la pa disponib.")

    if job.closes_at:
        closes = job.closes_at
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=timezone.utc)
        if closes <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Òf travay la fèmen.")

    email = payload.email.lower().strip()
    existing = db.query(Application).filter(
        Application.job_posting_id == job.id,
        Application.email == email,
    ).first()

    if existing:
        # Nou pa revele ke yon aplikasyon deja egziste. Nou mete ajou
        # sa ki la a epi nou bay menm resi a.
        existing.full_name = payload.full_name.strip()
        existing.phone = payload.phone or existing.phone
        existing.resume_url = payload.resume_url or existing.resume_url
        existing.cover_letter = payload.cover_letter or existing.cover_letter
        db.commit()
        app = existing
    else:
        app = Application(
            organization_id=org.id,
            job_posting_id=job.id,
            full_name=payload.full_name.strip(),
            email=email,
            phone=payload.phone,
            resume_url=payload.resume_url,
            cover_letter=payload.cover_letter,
            source=payload.source,
            stage=ApplicationStage.RECEIVED,
        )
        db.add(app)
        db.commit()
        db.refresh(app)

        if job.created_by_id:
            _notify(
                db, org.id, job.created_by_id,
                title="Nouvo aplikasyon",
                body=f"{app.full_name} aplike pou '{job.title}'.",
                link=f"/applications/{app.id}",
            )

    return ApplicationReceipt(
        application_id=app.id,
        job_title=job.title,
        company_name=org.name,
        message=(
            "Nou resevwa aplikasyon w. Ekip la ap gade l epi n ap kontakte w "
            "si pwofil ou koresponn ak pozisyon an."
        ),
    )


# ---------------------------------------------------------------------------
# LIS AK PIPLIN
# ---------------------------------------------------------------------------

class ApplicationRow(BaseModel):
    application: ApplicationOut
    job_title: str
    interview_count: int


class ApplicationListResponse(BaseModel):
    total: int
    items: list[ApplicationRow]


def _rows(db: Session, pairs) -> list[ApplicationRow]:
    out = []
    for app, job in pairs:
        count = db.query(func.count(Interview.id)).filter(
            Interview.application_id == app.id
        ).scalar() or 0
        out.append(ApplicationRow(
            application=ApplicationOut.model_validate(app),
            job_title=job.title,
            interview_count=count,
        ))
    return out


@router.get("", response_model=ApplicationListResponse, dependencies=[Depends(require_manager)])
def list_applications(
    org_id: TenantId,
    db: DbSession,
    job_posting_id: Optional[int] = None,
    stage: Optional[ApplicationStage] = None,
    q: Annotated[Optional[str], Query(description="Non oswa imel")] = None,
    min_rating: Annotated[Optional[int], Query(ge=1, le=5)] = None,
):
    query = (
        db.query(Application, JobPosting)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(Application.organization_id == org_id)
    )

    if job_posting_id is not None:
        query = query.filter(Application.job_posting_id == job_posting_id)
    if stage is not None:
        query = query.filter(Application.stage == stage)
    if min_rating is not None:
        query = query.filter(Application.rating >= min_rating)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            (Application.full_name.ilike(pattern)) | (Application.email.ilike(pattern))
        )

    pairs = query.order_by(Application.created_at.desc()).all()
    return ApplicationListResponse(total=len(pairs), items=_rows(db, pairs))


class StageColumn(BaseModel):
    stage: ApplicationStage
    count: int
    items: list[ApplicationOut]


class Pipeline(BaseModel):
    job_posting_id: int
    job_title: str
    openings: int
    total_applications: int
    columns: list[StageColumn]


@router.get(
    "/pipeline/{job_id}",
    response_model=Pipeline,
    dependencies=[Depends(require_manager)],
)
def hiring_pipeline(job_id: int, org_id: TenantId, db: DbSession):
    """Kandida yo gwoupe pa etap — pou yon tablo kanban nan frontend lan."""
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.organization_id == org_id,
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Òf travay la pa jwenn.")

    apps = db.query(Application).filter(
        Application.job_posting_id == job.id
    ).order_by(Application.rating.desc().nullslast(), Application.created_at).all()

    order = [
        ApplicationStage.RECEIVED,
        ApplicationStage.SCREENING,
        ApplicationStage.INTERVIEW,
        ApplicationStage.OFFER,
        ApplicationStage.HIRED,
        ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
    ]

    columns = []
    for st in order:
        items = [ApplicationOut.model_validate(a) for a in apps if a.stage == st]
        columns.append(StageColumn(stage=st, count=len(items), items=items))

    return Pipeline(
        job_posting_id=job.id,
        job_title=job.title,
        openings=job.openings or 1,
        total_applications=len(apps),
        columns=columns,
    )


class ApplicationDetail(BaseModel):
    application: ApplicationOut
    job_title: str
    internal_notes: Optional[str] = None
    rejected_reason: Optional[str] = None
    interviews: list[InterviewOut]


@router.get(
    "/{application_id}",
    response_model=ApplicationDetail,
    dependencies=[Depends(require_manager)],
)
def read_application(application_id: int, org_id: TenantId, db: DbSession):
    app = _get_application_or_404(db, org_id, application_id)
    job = db.query(JobPosting).filter(JobPosting.id == app.job_posting_id).first()

    interviews = db.query(Interview).filter(
        Interview.application_id == app.id
    ).order_by(Interview.round_number, Interview.scheduled_at).all()

    return ApplicationDetail(
        application=ApplicationOut.model_validate(app),
        job_title=job.title if job else "",
        internal_notes=app.internal_notes,
        rejected_reason=app.rejected_reason,
        interviews=[InterviewOut.model_validate(i) for i in interviews],
    )


@router.patch(
    "/{application_id}",
    response_model=ApplicationOut,
    dependencies=[Depends(require_manager)],
)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    org_id: TenantId,
    db: DbSession,
):
    """
    Chanje etap, nòt, oswa kòmantè entèn.
    Transisyon yo kontwole — yon moun pa ka pase de 'resevwa' dirèk
    a 'anboche' san etap yo nan mitan.
    """
    app = _get_application_or_404(db, org_id, application_id)
    data = payload.model_dump(exclude_unset=True)

    new_stage = data.get("stage")
    if new_stage is not None and new_stage != app.stage:
        allowed = ALLOWED_TRANSITIONS.get(app.stage, set())
        if new_stage not in allowed:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ou pa ka pase de '{app.stage.value}' a '{new_stage.value}'. "
                    f"Etap ki posib: {', '.join(sorted(s.value for s in allowed)) or 'okenn'}."
                ),
            )
        if new_stage == ApplicationStage.HIRED:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Pou anboche yon kandida, sèvi ak "
                    "POST /api/offers/{id}/hire — li kreye dosye anplwaye a."
                ),
            )

    for field, value in data.items():
        setattr(app, field, value)

    db.commit()
    db.refresh(app)
    return app


class RejectRequest(BaseModel):
    reason: str = Field(min_length=3)


@router.post(
    "/{application_id}/reject",
    response_model=ApplicationOut,
    dependencies=[Depends(require_manager)],
)
def reject_application(
    application_id: int,
    payload: RejectRequest,
    org_id: TenantId,
    db: DbSession,
):
    app = _get_application_or_404(db, org_id, application_id)

    if app.stage == ApplicationStage.HIRED:
        raise HTTPException(
            status_code=400,
            detail="Kandida a deja anboche.",
        )

    app.stage = ApplicationStage.REJECTED
    app.rejected_reason = payload.reason
    db.commit()
    db.refresh(app)
    return app


# ---------------------------------------------------------------------------
# ANTREVI
# ---------------------------------------------------------------------------

@router.post(
    "/{application_id}/interviews",
    response_model=InterviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_manager)],
)
def schedule_interview(
    application_id: int,
    payload: InterviewCreate,
    org_id: TenantId,
    db: DbSession,
):
    """
    Planifye yon antrevi. Aplikasyon an pase otomatikman nan etap
    'interview' si li te nan 'received' oswa 'screening'.
    """
    app = _get_application_or_404(db, org_id, application_id)

    if app.stage in (ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN):
        raise HTTPException(
            status_code=400,
            detail=f"Kandida a nan estati '{app.stage.value}'.",
        )

    if payload.interviewer_id is not None:
        interviewer = db.query(Employee).filter(
            Employee.id == payload.interviewer_id,
            Employee.organization_id == org_id,
        ).first()
        if interviewer is None:
            raise HTTPException(status_code=400, detail="Moun k ap fè antrevi a pa jwenn.")

    data = payload.model_dump(exclude={"application_id"})
    iv = Interview(organization_id=org_id, application_id=app.id, **data)
    db.add(iv)

    if app.stage in (ApplicationStage.RECEIVED, ApplicationStage.SCREENING):
        app.stage = ApplicationStage.INTERVIEW

    db.commit()
    db.refresh(iv)

    if payload.interviewer_id:
        interviewer = db.query(Employee).filter(
            Employee.id == payload.interviewer_id
        ).first()
        if interviewer and interviewer.user_id:
            _notify(
                db, org_id, interviewer.user_id,
                title="Antrevi planifye",
                body=(
                    f"Ou gen yon antrevi ak {app.full_name} "
                    f"nan {_format_local(db, org_id, payload.scheduled_at)}."
                ),
                link=f"/applications/{app.id}",
            )

    return iv


class InterviewResult(BaseModel):
    scheduled_at: Optional[UtcDatetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    score: Optional[int] = Field(default=None, ge=1, le=5)
    completed: Optional[bool] = None


@router.patch(
    "/interviews/{interview_id}",
    response_model=InterviewOut,
    dependencies=[Depends(require_manager)],
)
def update_interview(
    interview_id: int,
    payload: InterviewResult,
    org_id: TenantId,
    db: DbSession,
):
    iv = _get_interview_or_404(db, org_id, interview_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(iv, field, value)
    db.commit()
    db.refresh(iv)
    return iv


class UpcomingInterview(BaseModel):
    interview: InterviewOut
    candidate_name: str
    job_title: str
    interviewer_name: Optional[str] = None


class UpcomingResponse(BaseModel):
    total: int
    items: list[UpcomingInterview]


@router.get(
    "/interviews/upcoming",
    response_model=UpcomingResponse,
    dependencies=[Depends(require_manager)],
)
def upcoming_interviews(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    mine_only: bool = False,
):
    """Antrevi ki ap vini. `mine_only=true` pou sa m ap fè yo."""
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=days)

    q = (
        db.query(Interview, Application, JobPosting)
        .join(Application, Interview.application_id == Application.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(
            Interview.organization_id == org_id,
            Interview.completed.is_(False),
            Interview.scheduled_at >= now,
            Interview.scheduled_at <= until,
        )
    )

    if mine_only:
        me = db.query(Employee).filter(Employee.user_id == user.id).first()
        if me is None:
            return UpcomingResponse(total=0, items=[])
        q = q.filter(Interview.interviewer_id == me.id)

    rows = q.order_by(Interview.scheduled_at).all()

    items = []
    for iv, app, job in rows:
        name = None
        if iv.interviewer_id:
            emp = db.query(Employee).filter(Employee.id == iv.interviewer_id).first()
            if emp:
                name = f"{emp.first_name} {emp.last_name}"
        items.append(UpcomingInterview(
            interview=InterviewOut.model_validate(iv),
            candidate_name=app.full_name,
            job_title=job.title,
            interviewer_name=name,
        ))

    return UpcomingResponse(total=len(items), items=items)