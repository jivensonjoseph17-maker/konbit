from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import Leave, Employee, User
from app.schemas import LeaveCreate, LeaveResponse
from app.auth import get_current_user

router = APIRouter(prefix="/leaves", tags=["leaves"])

@router.post("", response_model=LeaveResponse)
def request_leave(leave: LeaveCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.user_id == current_user.id, Employee.is_active == True).first()
    if not employee:
        raise HTTPException(status_code=403, detail="Ou pa yon employe")
    
    days = (leave.end_date - leave.start_date).days + 1
    new_leave = Leave(
        employee_id=current_user.id,
        company_id=employee.company_id,
        leave_type=leave.leave_type,
        start_date=leave.start_date,
        end_date=leave.end_date,
        days_requested=days,
        reason=leave.reason
    )
    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)
    return new_leave

@router.get("/my")
def my_leaves(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Leave).filter(Leave.employee_id == current_user.id).order_by(Leave.requested_at.desc()).all()

@router.post("/{leave_id}/respond")
def respond_leave(leave_id: int, status: str, notes: str = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    leave = db.query(Leave).filter(Leave.id == leave_id).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Demann pa jwenn")
    
    leave.status = status
    leave.approved_by = current_user.id
    leave.responded_at = datetime.utcnow()
    leave.response_notes = notes
    db.commit()
    return {"message": f"Demann vakans {status}"}

@router.get("/balance")
def leave_balance(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    year_start = datetime(datetime.utcnow().year, 1, 1)
    used = db.query(Leave).filter(
        Leave.employee_id == current_user.id,
        Leave.status == "approved",
        Leave.start_date >= year_start
    ).all()
    total_used = sum(l.days_requested for l in used)
    total_allowed = 15
    return {"total_allowed": total_allowed, "used": total_used, "remaining": total_allowed - total_used}