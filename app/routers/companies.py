from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Company, User
from app.schemas import CompanyCreate, CompanyResponse
from app.auth import get_current_user

router = APIRouter(prefix="/companies", tags=["companies"])

@router.post("", response_model=CompanyResponse)
def create_company(company: CompanyCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.role not in ["employer", "manager", "admin"]:
        raise HTTPException(status_code=403, detail="Sèlman biznis ka kreye konpayi")
    
    if db.query(Company).filter(Company.owner_id == current_user.id).first():
        raise HTTPException(status_code=400, detail="Ou deja gen yon konpayi")
    
    new_company = Company(**company.dict(), owner_id=current_user.id)
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company

@router.get("/me", response_model=CompanyResponse)
def get_my_company(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Ou pa gen konpayi ankò")
    return company

@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Konpayi pa jwenn")
    return company