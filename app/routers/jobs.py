from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Job, Company, User
from app.schemas import JobCreate, JobUpdate, JobResponse
from app.security import get_current_user, require_roles
router = APIRouter()


@router.get("", response_model=List[JobResponse])
def list_jobs(
    q: Optional[str] = Query(None, description="Rechèch pa tit oswa deskripsyon"),
    location: Optional[str] = Query(None, description="Filtre pa kote"),
    job_type: Optional[str] = Query(None, description="Filtre pa tip travay"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Lis tout travay ki disponib (piblik) avèk opsyon filtre ak pajinasyon"""
    query = db.query(Job).filter(Job.is_active == True)

    if q:
        query = query.filter(
            or_(
                Job.title.ilike(f"%{q}%"),
                Job.description.ilike(f"%{q}%")
            )
        )
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if job_type:
        query = query.filter(Job.job_type == job_type)

    return query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/my", response_model=List[JobResponse])
def list_my_company_jobs(
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Lis tout travay konpayi itilizatè a pibliye (aktif ak inaktif)"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen yon konpayi ki anrejistre."
        )

    return db.query(Job).filter(Job.company_id == company.id).order_by(Job.created_at.desc()).all()


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    job_data: JobCreate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou dwe anrejistre yon konpayi anvan ou kreye yon travay."
        )

    new_job = Job(
        title=job_data.title,
        description=job_data.description,
        requirements=job_data.requirements,
        responsibilities=job_data.responsibilities,
        job_type=job_data.job_type,
        location=job_data.location,
        salary_min=job_data.salary_min,
        salary_max=job_data.salary_max,
        currency=job_data.currency or "HTG",
        company_id=company.id,
        posted_by=current_user.id,
        is_active=True
    )
    
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    """Wè detay sou yon travay espesifik"""
    job = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Travay sa a pa egziste oswa li pa disponib ankò."
        )
    return job


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    job_data: JobUpdate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Modifye yon ensèsyon travay"""
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
            detail="Ou pa gen pèmisyon pou modifye travay sa a."
        )

    update_dict = job_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(job, key, value)

    db.commit()
    db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Dezaktive yon travay"""
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
            detail="Ou pa gen pèmisyon pou efase travay sa a."
        )

    job.is_active = False
    db.commit()
    return None