from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Application, Job, User
from app.schemas import ApplicationCreate, ApplicationResponse
from app.auth import get_current_user

router = APIRouter(prefix="/applications", tags=["applications"])

@router.post("/{job_id}")
def apply_job(job_id: int, app: ApplicationCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role != "job_seeker":
        raise HTTPException(status_code=403, detail="Sèlman chèchè travay ka aplike")
    
    job = db.query(Job).filter(Job.id == job_id, Job.is_active == True).first()
    if not job:
        raise HTTPException(status_code=404, detail="Travay pa egziste")
    
    existing = db.query(Application).filter(
        Application.job_id == job_id,
        Application.applicant_id == current_user.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ou deja aplike pou travay sa")
    
    new_app = Application(job_id=job_id, applicant_id=current_user.id, cover_letter=app.cover_letter)
    db.add(new_app)
    db.commit()
    return {"message": "Aplikasyon soumèt avèk siksè!"}

@router.get("/my")
def my_applications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Application).filter(Application.applicant_id == current_user.id).all()

@router.get("/job/{job_id}")
def job_applications(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.company.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ou pa gen aksè")
    return db.query(Application).filter(Application.job_id == job_id).all()

@router.put("/{app_id}/status")
def update_status(app_id: int, status: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app or app.job.company.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ou pa gen aksè")
    app.status = status
    db.commit()
    return {"message": f"Status chanje pou {status}"}