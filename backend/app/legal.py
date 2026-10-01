"""
Konbit — Kondisyon itilizasyon, konfidansyalite, avètisman pewòl
Chemen: backend/app/legal.py

  - TERMS_VERSION: chanje l CHAK FWA tèks kondisyon/konfidansyalite yo
    chanje. Chak kont sere vèsyon li te aksepte a (User.terms_version).
  - Enskripsyon (biznis oswa kandida) refize si moun nan pa aksepte.
  - Avètisman pewòl: yon moun HR/admin konfime yon fwa pa biznis, avan
    premye apwobasyon pewòl la, ke KONMBIT se yon zouti e yon kontab dwe
    verifye chif yo (Organization.payroll_ack_*).

ENFORCE_*: conftest.py mete yo False pou ansyen tès yo; test_legal.py
aktive yo.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Organization, User

TERMS_VERSION = "2026-10-bouyon"

ENFORCE_TERMS = True
ENFORCE_PAYROLL_ACK = True

TERMS_REQUIRED = "Ou dwe aksepte kondisyon itilizasyon yo ak politik konfidansyalite a."
PAYROLL_ACK_REQUIRED = "Konfime avètisman pewòl la anvan premye apwobasyon an."


def require_terms(accepted: bool) -> None:
    if ENFORCE_TERMS and not accepted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=TERMS_REQUIRED)


def stamp_terms(user: User, accepted: bool) -> None:
    """Sere vèsyon tèks moun nan aksepte a. PA komite."""
    if accepted:
        user.terms_version = TERMS_VERSION
        user.terms_accepted_at = datetime.now(timezone.utc)


def require_payroll_ack(db: Session, org_id: int) -> None:
    if not ENFORCE_PAYROLL_ACK:
        return
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None or org.payroll_ack_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PAYROLL_ACK_REQUIRED)