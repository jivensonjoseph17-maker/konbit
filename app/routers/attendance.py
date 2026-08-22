from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from sqlalchemy import func
from app.database import get_db
from app.models import Attendance, Employee, User
from app.auth import get_current_user

router = APIRouter(prefix="/attendance", tags=["attendance"])

@router.post("/clock-in")
def clock_in(lat: float = None, lng: float = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.user_id == current_user.id, Employee.is_active == True).first()
    if not employee:
        raise HTTPException(status_code=403, detail="Ou pa yon employe anrejistre")
    
    today = datetime.utcnow().date()
    existing = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        func.date(Attendance.date) == today
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ou deja clock-in jodi a")
    
    att = Attendance(
        employee_id=current_user.id,
        company_id=employee.company_id,
        date=datetime.utcnow(),
        clock_in=datetime.utcnow(),
        clock_in_lat=lat,
        clock_in_lng=lng
    )
    db.add(att)
    db.commit()
    return {"message": "Clock-in siksè!", "time": att.clock_in}

@router.post("/clock-out")
def clock_out(lat: float = None, lng: float = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    att = db.query(Attendance).filter(
        Attendance.employee_id == current_user.id,
        func.date(Attendance.date) == today,
        Attendance.clock_out == None
    ).first()
    if not att:
        raise HTTPException(status_code=400, detail="Ou pa clock-in jodi a")
    
    att.clock_out = datetime.utcnow()
    att.clock_out_lat = lat
    att.clock_out_lng = lng
    delta = att.clock_out - att.clock_in
    att.total_hours = round(delta.total_seconds() / 3600, 2)
    db.commit()
    return {"message": "Clock-out siksè!", "total_hours": att.total_hours}

@router.get("/my")
def my_attendance(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Attendance).filter(Attendance.employee_id == current_user.id).order_by(Attendance.date.desc()).all()