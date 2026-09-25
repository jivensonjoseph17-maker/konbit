"""
Konbit — Router Òf Travay
Chemen: backend/app/routers/jobs.py

PIBLIK (san otantifikasyon — se paj karyè a):
    GET  /api/jobs/public/{org_slug}            Òf yon biznis
    GET  /api/jobs/public/{org_slug}/{slug}     Detay yon òf

ENTÈN (HR):
    GET    /api/jobs/careers-link    Lyen paj karyè biznis la (pou pataje)
    POST   /api/jobs                 Kreye yon òf
    GET    /api/jobs                 Lis òf yo
    GET    /api/jobs/{id}            Detay ak konte aplikasyon
    PATCH  /api/jobs/{id}            Modifye
    POST   /api/jobs/{id}/publish    Pibliye
    POST   /api/jobs/{id}/close      Fèmen
    POST   /api/jobs/{id}/reopen     Louvri ankò yon òf ki fèmen
    DELETE /api/jobs/{id}            Efase yon bouyon

ATANSYON SOU ENDPOINT PIBLIK YO: yo pa gen otantifikasyon, donk yo PA KA
sèvi ak `get_tenant`. Izolasyon an fèt sou `org_slug` nan URL la, epi yo
retounen SÈLMAN òf ki pibliye. Pa janm ajoute yon chan entèn
(`internal_notes`, `salary_min` lè `show_salary=False`) nan repons piblik la.

ESTATI A chanje SÈLMAN pa /publish, /close ak /reopen — pa pa PATCH.
Chak nan yo gen pwòp règ pa l (deskripsyon obligatwa, refi otomatik...).

DAT: `closes_at` dwe gen yon fizo orè (UtcDatetime) — li sere an UTC.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    Application,
    ApplicationStage,
    Department,
    JobPosting,
    JobStatus,
    Organization,
    Position,
)
from ..schemas import (
    JobPostingCreate,
    JobPostingOut,
    JobPostingPublic,
    JobPostingUpdate,
    Message,
    UtcDatetime,
)

logger = logging.getLogger("konbit")

router = APIRouter()


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Konvèti yon tit an slug pou URL. Aksan kreyòl yo tounen lèt senp."""
    replacements = {
        "à": "a", "á": "a", "â": "a", "ä": "a",
        "è": "e", "é": "e", "ê": "e", "ë": "e",
        "ì": "i", "í": "i", "î": "i", "ï": "i",
        "ò": "o", "ó": "o", "ô": "o", "ö": "o",
        "ù": "u", "ú": "u", "û": "u", "ü": "u",
        "ñ": "n", "ç": "c",
    }
    s = text.lower().strip()
    for old, new in replacements.items():
        s = s.replace(old, new)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:200] or "of-travay"


def _unique_slug(db: Session, org_id: int, title: str,
                 exclude_id: Optional[int] = None) -> str:
    base = _slugify(title)
    candidate = base
    counter = 2
    while True:
        q = db.query(JobPosting).filter(
            JobPosting.organization_id == org_id,
            JobPosting.slug == candidate,
        )
        if exclude_id:
            q = q.filter(JobPosting.id != exclude_id)
        if q.first() is None:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def _get_job_or_404(db: Session, org_id: int, job_id: int) -> JobPosting:
    job = db.query(JobPosting).filter(
        JobPosting.id == job_id,
        JobPosting.organization_id == org_id,
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Òf travay la pa jwenn.")
    return job


def _is_open(job: JobPosting) -> bool:
    """Yon òf louvri si li pibliye epi dat fèmti a poko rive."""
    if job.status != JobStatus.PUBLISHED:
        return False
    if job.closes_at is None:
        return True
    closes = job.closes_at
    if closes.tzinfo is None:
        closes = closes.replace(tzinfo=timezone.utc)
    return closes > datetime.now(timezone.utc)


def _to_public(job: JobPosting, company_name: Optional[str]) -> JobPostingPublic:
    """
    Vèsyon piblik la. Nou konstwi l chan pa chan eksprè: konsa si yon jou
    yon moun ajoute yon chan sansib nan modèl la, li p ap koule isit.
    """
    return JobPostingPublic(
        id=job.id,
        title=job.title,
        slug=job.slug,
        description=job.description,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
        location=job.location,
        is_remote=bool(job.is_remote),
        employment_type=job.employment_type,
        openings=job.openings or 1,
        published_at=job.published_at,
        closes_at=job.closes_at,
        company_name=company_name,
        # Salè a parèt SÈLMAN si HR chwazi montre l
        salary_min=job.salary_min if job.show_salary else None,
        salary_max=job.salary_max if job.show_salary else None,
        currency=job.currency if job.show_salary else None,
    )


def _to_out(db: Session, job: JobPosting) -> JobPostingOut:
    count = db.query(func.count(Application.id)).filter(
        Application.job_posting_id == job.id
    ).scalar() or 0

    out = JobPostingOut.model_validate(job)
    out.application_count = count
    return out


# ---------------------------------------------------------------------------
# PAJ KARYÈ PIBLIK — SAN OTANTIFIKASYON
# ---------------------------------------------------------------------------

class PublicJobList(BaseModel):
    company_name: str
    company_logo: Optional[str] = None
    total: int
    items: list[JobPostingPublic]


@router.get("/public/{org_slug}", response_model=PublicJobList, tags=["Piblik"])
def public_jobs(
    org_slug: str,
    db: DbSession,
    q: Annotated[Optional[str], Query(description="Rechèch sou tit")] = None,
    location: Optional[str] = None,
    remote_only: bool = False,
):
    """
    Paj karyè yon biznis. Pa gen otantifikasyon — nenpòt moun ka wè l.
    Sèlman òf ki PIBLIYE epi ki poko fèmen parèt.
    """
    org = db.query(Organization).filter(
        Organization.slug == org_slug.lower().strip(),
        Organization.is_active.is_(True),
    ).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Biznis la pa jwenn.")

    query = db.query(JobPosting).filter(
        JobPosting.organization_id == org.id,
        JobPosting.status == JobStatus.PUBLISHED,
    )

    if q:
        query = query.filter(JobPosting.title.ilike(f"%{q.strip()}%"))
    if location:
        query = query.filter(JobPosting.location.ilike(f"%{location.strip()}%"))
    if remote_only:
        query = query.filter(JobPosting.is_remote.is_(True))

    jobs = [j for j in query.order_by(JobPosting.published_at.desc()).all() if _is_open(j)]

    return PublicJobList(
        company_name=org.name,
        company_logo=org.logo_url,
        total=len(jobs),
        items=[_to_public(j, org.name) for j in jobs],
    )


@router.get("/public/{org_slug}/{job_slug}", response_model=JobPostingPublic, tags=["Piblik"])
def public_job_detail(org_slug: str, job_slug: str, db: DbSession):
    """Detay yon òf. Chak vizit monte konte a."""
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
    if job is None or not _is_open(job):
        raise HTTPException(status_code=404, detail="Òf travay la pa disponib.")

    job.view_count = (job.view_count or 0) + 1
    db.commit()

    return _to_public(job, org.name)


# ---------------------------------------------------------------------------
# JESYON ÒF (HR)
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=JobPostingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_job(
    payload: JobPostingCreate,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    if payload.department_id is not None:
        ok = db.query(Department).filter(
            Department.id == payload.department_id,
            Department.organization_id == org_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Depatman an pa jwenn.")

    if payload.position_id is not None:
        ok = db.query(Position).filter(
            Position.id == payload.position_id,
            Position.organization_id == org_id,
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Pozisyon an pa jwenn.")

    if payload.salary_min and payload.salary_max and payload.salary_min > payload.salary_max:
        raise HTTPException(
            status_code=400,
            detail="Salè minimòm nan pa ka pi wo pase maksimòm nan.",
        )

    job = JobPosting(
        organization_id=org_id,
        created_by_id=user.id,
        slug=_unique_slug(db, org_id, payload.title),
        status=JobStatus.DRAFT,
        view_count=0,
        **payload.model_dump(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_out(db, job)


class JobListResponse(BaseModel):
    total: int
    items: list[JobPostingOut]


@router.get("", response_model=JobListResponse, dependencies=[Depends(require_hr)])
def list_jobs(
    org_id: TenantId,
    db: DbSession,
    status_filter: Annotated[Optional[JobStatus], Query(alias="status")] = None,
    department_id: Optional[int] = None,
    q: Optional[str] = None,
):
    query = db.query(JobPosting).filter(JobPosting.organization_id == org_id)

    if status_filter:
        query = query.filter(JobPosting.status == status_filter)
    if department_id is not None:
        query = query.filter(JobPosting.department_id == department_id)
    if q:
        query = query.filter(JobPosting.title.ilike(f"%{q.strip()}%"))

    items = query.order_by(JobPosting.created_at.desc()).all()
    return JobListResponse(total=len(items), items=[_to_out(db, j) for j in items])


class CareersLink(BaseModel):
    org_slug: str
    company_name: str
    path: str


@router.get("/careers-link", response_model=CareersLink, dependencies=[Depends(require_hr)])
def careers_link(org_id: TenantId, db: DbSession):
    """
    Idantifyan paj karyè a, pou HR kopye lyen an san l pa bezwen konnen slug la.
    DWE rete ANVAN /{job_id}: sinon "careers-link" ta pase pou yon id.
    """
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Biznis la pa jwenn.")
    return CareersLink(
        org_slug=org.slug,
        company_name=org.name,
        path=f"careers.html?org={org.slug}",
    )


@router.get("/{job_id}", response_model=JobPostingOut, dependencies=[Depends(require_hr)])
def read_job(job_id: int, org_id: TenantId, db: DbSession):
    return _to_out(db, _get_job_or_404(db, org_id, job_id))


@router.patch("/{job_id}", response_model=JobPostingOut, dependencies=[Depends(require_hr)])
def update_job(
    job_id: int,
    payload: JobPostingUpdate,
    org_id: TenantId,
    db: DbSession,
):
    job = _get_job_or_404(db, org_id, job_id)
    data = payload.model_dump(exclude_unset=True)

    # Estati a pa chanje isit. San sa, yon PATCH {"status": "published"}
    # ta pibliye yon òf san deskripsyon, oswa fèmen l san refize kandida yo.
    if "status" in data and data["status"] != job.status:
        raise HTTPException(
            status_code=400,
            detail="Pou chanje estati a, sèvi ak Pibliye, Fèmen oswa Louvri ankò.",
        )
    data.pop("status", None)

    if "openings" in data and (data["openings"] is None or data["openings"] < 1):
        raise HTTPException(status_code=400, detail="Dwe gen omwen yon pòs louvri.")

    # Si tit la chanje, slug la swiv — men sèlman pandan li bouyon.
    # Chanje slug yon òf ki pibliye kase lyen moun deja pataje yo.
    if "title" in data and data["title"] != job.title and job.status == JobStatus.DRAFT:
        job.slug = _unique_slug(db, org_id, data["title"], exclude_id=job.id)

    for field, value in data.items():
        setattr(job, field, value)

    if job.salary_min and job.salary_max and job.salary_min > job.salary_max:
        raise HTTPException(
            status_code=400,
            detail="Salè minimòm nan pa ka pi wo pase maksimòm nan.",
        )

    db.commit()
    db.refresh(job)
    return _to_out(db, job)


class PublishJobRequest(BaseModel):
    closes_at: Optional[UtcDatetime] = None


@router.post(
    "/{job_id}/publish",
    response_model=JobPostingOut,
    dependencies=[Depends(require_hr)],
)
def publish_job(
    job_id: int,
    payload: PublishJobRequest,
    org_id: TenantId,
    db: DbSession,
):
    """
    Pibliye yon òf sou paj karyè a. Nou mande yon deskripsyon —
    yon òf san deskripsyon ap parèt vid pou kandida yo.
    """
    job = _get_job_or_404(db, org_id, job_id)

    if job.status == JobStatus.PUBLISHED:
        raise HTTPException(status_code=400, detail="Òf la deja pibliye.")
    if not (job.description or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Ajoute yon deskripsyon anvan ou pibliye.",
        )

    job.status = JobStatus.PUBLISHED
    job.published_at = datetime.now(timezone.utc)
    if payload.closes_at:
        job.closes_at = payload.closes_at

    db.commit()
    db.refresh(job)
    return _to_out(db, job)


class CloseJobRequest(BaseModel):
    reject_pending: bool = False
    rejection_note: Optional[str] = None


class CloseJobResult(BaseModel):
    job: JobPostingOut
    rejected_applications: int


@router.post(
    "/{job_id}/close",
    response_model=CloseJobResult,
    dependencies=[Depends(require_hr)],
)
def close_job(
    job_id: int,
    payload: CloseJobRequest,
    org_id: TenantId,
    db: DbSession,
):
    """
    Fèmen yon òf. Ak `reject_pending=true`, tout kandida ki rete nan
    etap early yo ap refize — konsa pesonn pa rete ap tann pou tout tan.
    """
    job = _get_job_or_404(db, org_id, job_id)
    job.status = JobStatus.CLOSED

    rejected = 0
    if payload.reject_pending:
        pending = db.query(Application).filter(
            Application.job_posting_id == job.id,
            Application.stage.in_([
                ApplicationStage.RECEIVED,
                ApplicationStage.SCREENING,
                ApplicationStage.INTERVIEW,
            ]),
        ).all()
        for app in pending:
            app.stage = ApplicationStage.REJECTED
            app.rejected_reason = payload.rejection_note or "Pozisyon an fèmen."
            rejected += 1

    db.commit()
    db.refresh(job)
    return CloseJobResult(job=_to_out(db, job), rejected_applications=rejected)


@router.post(
    "/{job_id}/reopen",
    response_model=JobPostingOut,
    dependencies=[Depends(require_hr)],
)
def reopen_job(job_id: int, org_id: TenantId, db: DbSession):
    """
    Remèt yon òf FÈMEN tounen PIBLIYE.

    Sèlman yon òf ki nan estati FÈMEN ka louvri ankò — yon bouyon dwe
    toujou pase pa /publish (li mande yon deskripsyon anvan). Nou pa
    manyen `closes_at`: si dat fèmti a deja pase, òf la ap parèt fèmen
    ankò sou paj karyè a jouk HR ajiste dat la nan panèl "Detay òf la".
    """
    job = _get_job_or_404(db, org_id, job_id)
    if job.status != JobStatus.CLOSED:
        raise HTTPException(
            status_code=400,
            detail="Sèlman yon òf ki FÈMEN ka louvri ankò.",
        )
    job.status = JobStatus.PUBLISHED
    db.commit()
    db.refresh(job)
    return _to_out(db, job)


@router.delete("/{job_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_job(job_id: int, org_id: TenantId, db: DbSession):
    """Sèlman yon bouyon san aplikasyon. Sinon fèmen l."""
    job = _get_job_or_404(db, org_id, job_id)

    count = db.query(func.count(Application.id)).filter(
        Application.job_posting_id == job.id
    ).scalar() or 0
    if count:
        raise HTTPException(
            status_code=400,
            detail=f"{count} moun aplike. Fèmen òf la olye ou efase l.",
        )
    if job.status != JobStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail="Sèlman yon bouyon ka efase. Fèmen òf la pito.",
        )

    db.delete(job)
    db.commit()
    return Message(detail="Òf la efase.")