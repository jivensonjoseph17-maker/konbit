from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Job, Company, User
from app.schemas import JobCreate, JobResponse
from app.auth import get_current_user

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", response_model=JobResponse)
def create_job(job: JobCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Ou bezwen kreye yon konpayi anvan")
    
    new_job = Job(**job.dict(), company_id=company.id, posted_by=current_user.id)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

@router.get("")
def list_jobs(location: str = None, job_type: str = None, db: Session = Depends(get_db)):
    query = db.query(Job).filter(Job.is_active == True)
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if job_type:
        query = query.filter(Job.job_type == job_type)
    return query.order_by(Job.created_at.desc()).all()

@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Travay pa jwenn")
    return job

@router.delete("/{job_id}")
def delete_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.company.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ou pa gen aksè")
    job.is_active = False
    db.commit()
    return {"message": "Travay retire"}