from datetime import datetime, date, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Leave, Employee, Company, User
from app.schemas import LeaveCreate, LeaveResponse, LeaveStatusUpdate
from app.security import get_current_user, require_roles

router = APIRouter()


@router.post("", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
def request_leave(
    leave_data: LeaveCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fè yon demann konje kòm anplwaye"""
    emp = db.query(Employee).filter(
        Employee.user_id == current_user.id, 
        Employee.is_active == True
    ).first()
    
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Ou dwe yon anplwaye aktif nan yon konpayi pou w ka mande konje."
        )

    if leave_data.end_date < leave_data.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Dat fini an pa ka anvan dat kòmansman an."
        )

    days_requested = (leave_data.end_date - leave_data.start_date).days + 1

    new_leave = Leave(
        employee_id=emp.id,
        user_id=current_user.id,
        leave_type=leave_data.leave_type,
        start_date=leave_data.start_date,
        end_date=leave_data.end_date,
        days_requested=days_requested,
        reason=leave_data.reason,
        status="pending"
    )
    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)
    return new_leave


@router.get("/my", response_model=List[LeaveResponse])
def my_leaves(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Istwa demann konje pou itilizatè k ap konekte a"""
    return db.query(Leave).filter(
        Leave.user_id == current_user.id
    ).order_by(Leave.created_at.desc()).all()


@router.get("/pending", response_model=List[LeaveResponse])
def pending_leaves(
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Lis demann konje ki annatant sèlman pou konpayi itilizatè k ap jere a"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen yon konpayi ki anrejistre."
        )

    return db.query(Leave).join(Employee).filter(
        Employee.company_id == company.id,
        Leave.status == "pending"
    ).order_by(Leave.created_at.desc()).all()


@router.get("/company", response_model=List[LeaveResponse])
def all_company_leaves(
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Istwa tout konje nan konpayi an (soumèt, apwouve, oswa refize)"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen yon konpayi ki anrejistre."
        )

    return db.query(Leave).join(Employee).filter(
        Employee.company_id == company.id
    ).order_by(Leave.created_at.desc()).all()


@router.put("/{leave_id}/status", response_model=LeaveResponse)
def update_leave_status(
    leave_id: int,
    status_update: LeaveStatusUpdate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Apwouve oswa refize yon demann konje"""
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Demann konje sa a pa jwenn."
        )

    emp = db.query(Employee).filter(Employee.id == leave.employee_id).first()
    company = db.query(Company).filter(Company.id == emp.company_id).first() if emp else None

    if not company or company.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Ou pa gen pèmisyon pou w trete konje pou anplwaye sa a."
        )

    leave.status = status_update.status
    leave.approved_by = current_user.id
    leave.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(leave)
    return leave