import os
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Company, User
from app.schemas import CompanyCreate, CompanyUpdate, CompanyResponse
from app.security import get_current_user, require_roles

router = APIRouter()

@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    company_data: CompanyCreate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    existing = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou deja gen yon konpayi ki anrejistre."
        )

    new_company = Company(
        name=company_data.name,
        description=company_data.description,
        industry=company_data.industry,
        location=company_data.location,
        phone=company_data.phone,
        email=company_data.email,
        rnc=company_data.rnc,
        nif=company_data.nif,
        owner_id=current_user.id
    )
    db.add(new_company)
    db.commit()
    db.refresh(new_company)
    return new_company


@router.get("", response_model=List[CompanyResponse])
def get_all_companies(
    skip: int = 0, 
    limit: int = 20, 
    db: Session = Depends(get_db)
):
    return db.query(Company).offset(skip).limit(limit).all()


@router.get("/me", response_model=CompanyResponse)
def get_my_company(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen okenn konpayi ki anrejistre."
        )
    return company


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Konpayi sa a pa egziste."
        )
    return company


@router.put("/me", response_model=CompanyResponse)
def update_my_company(
    company_data: CompanyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Konpayi pa jwenn."
        )

    update_dict = company_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(company, key, value)

    db.commit()
    db.refresh(company)
    return company


@router.post("/me/logo")
async def upload_company_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Konpayi pa jwenn."
        )

    allowed_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Fòma fichiye sa a pa sipòte. Sèvi ak PNG, JPG oswa WEBP."
        )

    uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "logos"))
    os.makedirs(uploads_dir, exist_ok=True)

    filename = f"logo_company_{company.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(uploads_dir, filename)

    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    company.logo_url = f"/uploads/logos/{filename}"
    db.commit()

    return {"message": "Logo moute ak siksè!", "logo_url": company.logo_url}