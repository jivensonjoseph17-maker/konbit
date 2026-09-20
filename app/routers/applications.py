from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Application, Job, User, Company
from app.schemas import ApplicationCreate, ApplicationStatusUpdate, ApplicationResponse
from app.security import get_current_user, require_roles

router = APIRouter()


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply_job(
    app_data: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soumèt yon aplikasyon pou yon poste travay"""
    job = db.query(Job).filter(Job.id == app_data.job_id, Job.is_active == True).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Travay sa a pa egziste oswa li pa disponib ankò."
        )

    existing = db.query(Application).filter(
        Application.job_id == app_data.job_id,
        Application.applicant_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou deja aplike pou travay sa a."
        )

    new_app = Application(
        job_id=app_data.job_id,
        applicant_id=current_user.id,
        cover_letter=app_data.cover_letter,
        resume_url=app_data.resume_url,
        status="pending"
    )
    db.add(new_app)
    db.commit()
    db.refresh(new_app)
    return new_app


@router.get("/my", response_model=List[ApplicationResponse])
def my_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Lis tout aplikasyon itilizatè k ap konekte a te voye"""
    return db.query(Application).filter(
        Application.applicant_id == current_user.id
    ).order_by(Application.created_at.desc()).all()


@router.get("/job/{job_id}", response_model=List[ApplicationResponse])
def job_applications(
    job_id: int,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Lis tout aplikasyon ki soumèt pou yon travay espesifik (Sèlman mèt konpayi an)"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Travay sa a pa jwenn."
        )

    company = db.query(Company).filter(Company.id == job.company_id).first()
    if not company or company.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Ou pa gen aksè pou wè aplikasyon pou travay sa a."
        )

    return db.query(Application).filter(
        Application.job_id == job_id
    ).order_by(Application.created_at.desc()).all()


@router.put("/{app_id}/status", response_model=ApplicationResponse)
def update_application_status(
    app_id: int,
    status_update: ApplicationStatusUpdate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Mete ajou status yon aplikasyon (pending, interview, accepted, rejected)"""
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Aplikasyon sa a pa jwenn."
        )

    job = db.query(Job).filter(Job.id == app.job_id).first()
    company = db.query(Company).filter(Company.id == job.company_id).first() if job else None

    if not company or company.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Ou pa gen pèmisyon pou modifye aplikasyon sa a."
        )

    app.status = status_update.status
    db.commit()
    db.refresh(app)
    return app