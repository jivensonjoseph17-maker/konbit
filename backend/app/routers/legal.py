"""
Konbit — Router legal
Chemen: backend/app/routers/legal.py   (prefix /api/legal)

    GET  /terms            Vèsyon tèks kondisyon yo kounye a (piblik)
    POST /accept-terms     Kont mwen aksepte vèsyon kounye a
    GET  /payroll-ack      Estati avètisman pewòl biznis la (HR)
    POST /payroll-ack      HR/admin konfime avètisman pewòl la (yon sèl fwa)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..legal import TERMS_VERSION, stamp_terms
from ..login_guard import client_ip
from ..models import AuditLog, Organization, User

router = APIRouter()


class TermsInfo(BaseModel):
    version: str


@router.get("/terms", response_model=TermsInfo)
def terms_version():
    return TermsInfo(version=TERMS_VERSION)


class MyTerms(BaseModel):
    current_version: str
    accepted_version: Optional[str] = None
    accepted_at: Optional[datetime] = None


@router.post("/accept-terms", response_model=MyTerms)
def accept_terms(user: CurrentUser, db: DbSession):
    stamp_terms(user, True)
    db.commit()
    db.refresh(user)
    return MyTerms(current_version=TERMS_VERSION, accepted_version=user.terms_version,
                   accepted_at=user.terms_accepted_at)


class PayrollAck(BaseModel):
    accepted: bool
    accepted_at: Optional[datetime] = None
    accepted_by: Optional[str] = None


def _ack_out(db, org: Organization) -> PayrollAck:
    by = None
    if org.payroll_ack_by_id:
        who = db.query(User).filter(User.id == org.payroll_ack_by_id).first()
        by = who.full_name if who else None
    return PayrollAck(accepted=org.payroll_ack_at is not None,
                      accepted_at=org.payroll_ack_at, accepted_by=by)


@router.get("/payroll-ack", response_model=PayrollAck, dependencies=[Depends(require_hr)])
def payroll_ack_status(org_id: TenantId, db: DbSession):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    return _ack_out(db, org)


@router.post("/payroll-ack", response_model=PayrollAck, dependencies=[Depends(require_hr)])
def payroll_ack(user: CurrentUser, org_id: TenantId, request: Request, db: DbSession):
    """Premye konfimasyon an rete: kiyès ak ki lè (pou odit)."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org.payroll_ack_at is None:
        org.payroll_ack_at = datetime.now(timezone.utc)
        org.payroll_ack_by_id = user.id
        db.add(AuditLog(
            organization_id=org_id, user_id=user.id, action="payroll_ack",
            entity_type="organization", entity_id=org_id,
            changes="KONMBIT se yon zouti; biznis la responsab deklarasyon l yo; yon kontab dwe verifye chif yo.",
            ip_address=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
        db.refresh(org)
    return _ack_out(db, org)