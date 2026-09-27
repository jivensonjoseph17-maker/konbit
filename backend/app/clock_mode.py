"""
Konbit — Mòd pwentaj biznis la
Chemen: backend/app/clock_mode.py

    "phone"  Anplwaye yo pwente sou telefòn yo (tablo de bò). Pa defo.
    "kiosk"  Sèlman sou tablèt biznis la, ak nimewo + kòd pèsonèl.
             API a refize klòk in / klòk out pa telefòn.
    "both"   Toulède.

Fichye sa a separe pou attendance.py ak kiosk.py ka tou de sèvi avè l
san youn pa enpòte lòt an won.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Organization

PHONE = "phone"
KIOSK = "kiosk"
BOTH = "both"
CLOCK_MODES = (PHONE, KIOSK, BOTH)


def get_clock_mode(db: Session, org_id: int) -> str:
    mode = db.query(Organization.clock_mode).filter(Organization.id == org_id).scalar()
    return mode if mode in CLOCK_MODES else PHONE


def ensure_phone_clock_allowed(db: Session, org_id: int) -> None:
    """Rele nan attendance.py anvan klòk in / klòk out pa telefòn."""
    if get_clock_mode(db, org_id) == KIOSK:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Biznis ou a mande pou w pwente sou tablèt biznis la.",
        )