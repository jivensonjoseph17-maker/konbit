from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Offer, Company, User, Employee
from app.schemas import OfferCreate, OfferStatusUpdate, OfferResponse
from app.security import get_current_user, require_roles

router = APIRouter()


@router.get("/my", response_model=List[OfferResponse])
def my_received_offers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retounen tout òf travay yon chèchè travay resevwa"""
    return db.query(Offer).filter(
        Offer.user_id == current_user.id
    ).order_by(Offer.created_at.desc()).all()


@router.get("/sent", response_model=List[OfferResponse])
def sent_offers(
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Lis tout òf travay konpayi an voye bay kandida yo"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Ou pa gen yon konpayi ki anrejistre."
        )

    return db.query(Offer).filter(
        Offer.company_id == company.id
    ).order_by(Offer.created_at.desc()).all()


@router.post("", response_model=OfferResponse, status_code=status.HTTP_201_CREATED)
def create_offer(
    offer_data: OfferCreate,
    current_user: User = Depends(require_roles(["employer", "hr_manager", "admin"])),
    db: Session = Depends(get_db)
):
    """Kreye epi voye yon òf travay bay yon kandida"""
    company = db.query(Company).filter(Company.owner_id == current_user.id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ou dwe gen yon konpayi anvan ou voye yon òf travay."
        )

    applicant = db.query(User).filter(User.id == offer_data.applicant_id).first()
    if not applicant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Kandida sa a pa egziste."
        )

    new_offer = Offer(
        company_id=company.id,
        user_id=offer_data.applicant_id,
        job_id=offer_data.job_id,
        salary=offer_data.salary,
        start_date=offer_data.start_date,
        notes=getattr(offer_data, "notes", None),
        status="pending"
    )
    db.add(new_offer)
    db.commit()
    db.refresh(new_offer)
    return new_offer


@router.put("/{offer_id}/status", response_model=OfferResponse)
def update_offer_status(
    offer_id: int,
    status_update: OfferStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aksepte oswa refize yon òf travay (Sèlman kandida ki resevwa l la)"""
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Òf sa a pa egziste."
        )

    if offer.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Ou pa gen pèmisyon pou modifye estati òf sa a."
        )

    if status_update.status not in ["accepted", "rejected"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Estati a dwe 'accepted' oswa 'rejected'."
        )

    offer.status = status_update.status

    if status_update.status == "accepted":
        existing_employee = db.query(Employee).filter(
            Employee.user_id == current_user.id,
            Employee.company_id == offer.company_id
        ).first()

        if not existing_employee:
            new_employee = Employee(
                user_id=current_user.id,
                company_id=offer.company_id,
                position="Nouvo Anplwaye",
                base_salary=offer.salary,
                hire_date=offer.start_date,
                is_active=True
            )
            db.add(new_employee)

    db.commit()
    db.refresh(offer)
    return offer