from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import Offer, Application, User
from app.schemas import OfferCreate, OfferResponse
from app.auth import get_current_user

router = APIRouter(prefix="/offers", tags=["offers"])

@router.post("", response_model=OfferResponse)
def create_offer(offer: OfferCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(Application).filter(Application.id == offer.application_id).first()
    if not app or app.job.company.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ou pa gen aksè")
    
    new_offer = Offer(**offer.dict(), user_id=current_user.id)
    db.add(new_offer)
    db.commit()
    db.refresh(new_offer)
    return new_offer

@router.post("/{offer_id}/send")
def send_offer(offer_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.id == offer_id, Offer.sent_by == current_user.id).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Of pa jwenn")
    offer.status = "sent"
    offer.sent_at = datetime.utcnow()
    db.commit()
    return {"message": "Of lèt voye bay kandida a"}

@router.post("/{offer_id}/respond")
def respond_offer(offer_id: int, action: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer or offer.application.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Ou pa gen aksè")
    
    if action not in ["accept", "decline"]:
        raise HTTPException(status_code=400, detail="Aksyon pa valab")
    
    offer.status = "accepted" if action == "accept" else "declined"
    offer.responded_at = datetime.utcnow()
    db.commit()
    return {"message": f"Of la {action}ed"}