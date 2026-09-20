from datetime import datetime, date, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Attendance, Employee, Company, User
from app.schemas import AttendanceResponse
from app.security import get_current_user, require_roles

router = APIRouter()


@router.post("/clock-in", response_model=dict)
def clock_in(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pointe antre pou jounen an"""
    emp = db.query(Employee).filter(
        Employee.user_id == current_user.id,
        Employee.is_active == True
    ).first()

    if not emp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ou dwe yon anplwaye aktif nan yon konpayi pou w ka pointe."
        )

    today = date.today()
    now_utc = datetime.now(timezone.utc)

    existing = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if existing and existing.check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou deja pointe antre jodi a!"
        )

    if not existing:
        attendance = Attendance(
            employee_id=emp.id,
            user_id=current_user.id,
            date=today,
            check_in=now_utc,
            status="nan_travay"
        )
        db.add(attendance)
    else:
        attendance = existing
        attendance.check_in = now_utc
        attendance.status = "nan_travay"

    db.commit()
    db.refresh(attendance)

    return {
        "message": "Check-in reyisi!",
        "time": now_utc.strftime("%H:%M"),
        "status": "nan_travay"
    }


@router.post("/clock-out", response_model=dict)
def clock_out(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pointe soti pou jounen an"""
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance or not attendance.check_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou poko fè check-in jodi a!"
        )

    if attendance.check_out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou deja fè check-out jodi a!"
        )

    attendance.check_out = now_utc
    attendance.status = "fini"

    # Kalkile total èdtan
    check_in_time = attendance.check_in
    if check_in_time.tzinfo is None:
        check_in_time = check_in_time.replace(tzinfo=timezone.utc)

    duration = now_utc - check_in_time
    hours = duration.total_seconds() / 3600
    attendance.total_hours = round(hours, 2)

    db.commit()

    return {
        "message": "Check-out reyisi!",
        "check_out": now_utc.strftime("%H:%M"),
        "total_hours": attendance.total_hours,
        "status": "fini"
    }


@router.get("/today", response_model=dict)
def get_today_attendance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pointaj jodi a pou itilizatè a"""
    today = date.today()
    attendance = db.query(Attendance).filter(
        Attendance.user_id == current_user.id,
        Attendance.date == today
    ).first()

    if not attendance:
        return {
            "status": "pa_koumanse",
            "check_in": None,
            "check_out": None,
            "total_hours": 0.0
        }

    return {
        "status": attendance.status,
        "check_in": attendance.check_in.strftime("%H:%M") if attendance.check_in else None,
        "check_out": attendance.check_out.strftime("%H:%M") if attendance.check_out else None,
        "total_hours": attendance.total_hours or 0.0
    }


@router.get("/my", response_model=List[AttendanceResponse])
def my_attendance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(30, ge=1, le=100)
):
    """Istwa prezans itilizatè k ap konekte a"""
    return db.query(Attendance).filter(
        Attendance.user_id == current_user.id
    ).order_by(Attendance.date.desc()).limit(limit).all()


@router.get("/company", response_model=List[AttendanceResponse])
def company_attendance(
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """Rapò prezans tout anplwaye yon konpayi (sèlman pou mèt konpayi ak manajè)"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen yon konpayi ki anrejistre."
        )

    query = db.query(Attendance).join(Employee).filter(
        Employee.company_id == company.id
    )

    if start_date:
        query = query.filter(Attendance.date >= start_date)
    if end_date:
        query = query.filter(Attendance.date <= end_date)

    return query.order_by(Attendance.date.desc()).all()