"""
Konbit — Done biznis la: ekspòtasyon konplè ak fèmti kont
Chemen: backend/app/routers/org_data.py   (prefix /api/org-data)

    POST /export   ZIP ak yon CSV pa kalite done (administratè, modpas obligatwa)
    POST /close    Fèmen biznis la (administratè, modpas + non biznis la egzak)

FÈMTI: biznis la DEZAKTIVE touswit (deps.py refize tout demann, paj karyè a
disparèt). Done yo rete CLOSURE_GRACE_DAYS jou, pou yon erè ka korije
(kontak@konmbit.com). Apre sa, backend/scripts/purge_closed_orgs.py efase yo nèt.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..deps import CurrentUser, DbSession, TenantId, require_admin
from ..login_guard import client_ip
from ..mailer import send_email
from ..models import AuditLog, Organization, User, UserRole
from ..org_data import CLOSURE_GRACE_DAYS, build_export_zip
from ..schemas import Message
from ..security import verify_password

router = APIRouter()


class PasswordConfirm(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class CloseRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm_name: str = Field(min_length=1, max_length=200)


def _check_password(user: User, password: str) -> None:
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Modpas aktyèl la pa kòrèk.")


def _audit(db, request: Request, user: User, org_id: int, action: str, changes: str) -> None:
    db.add(AuditLog(
        organization_id=org_id, user_id=user.id, action=action,
        entity_type="organization", entity_id=org_id, changes=changes,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()


@router.post("/export", dependencies=[Depends(require_admin)])
def export_all_data(payload: PasswordConfirm, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    """Tout done biznis la nan yon ZIP (CSV). Chak ekspòtasyon ekri nan jounal odit la."""
    _check_password(user, payload.password)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    content = build_export_zip(db, org_id)
    _audit(db, request, user, org_id, "export_all_data", f"{len(content)} octets.")

    slug = "".join(c for c in (org.slug or "biznis") if c.isalnum() or c == "-")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="konmbit-{slug}-{stamp}.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/close", response_model=Message, dependencies=[Depends(require_admin)])
def close_business(payload: CloseRequest, user: CurrentUser, org_id: TenantId,
                   request: Request, background: BackgroundTasks, db: DbSession):
    _check_password(user, payload.password)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if payload.confirm_name.strip().casefold() != (org.name or "").strip().casefold():
        raise HTTPException(status_code=400, detail="Tape non biznis la egzakteman pou konfime.")

    org.is_active = False
    org.closure_requested_at = datetime.now(timezone.utc)
    org.closed_by_id = user.id
    # Tout sesyon biznis la mouri touswit, refresh token yo tou: yon lòt onglè
    # pa ka renouvle sesyon an apre fèmti a.
    db.query(User).filter(User.organization_id == org_id).update(
        {User.token_version: User.token_version + 1}, synchronize_session=False)
    _audit(db, request, user, org_id, "close_organization",
           f"Fèmen pa {user.email}. Efasman nèt apre {CLOSURE_GRACE_DAYS} jou.")

    admins = db.query(User).filter(
        User.organization_id == org_id,
        User.role.in_([UserRole.ORG_ADMIN, UserRole.SUPER_ADMIN]),
    ).all()
    text = (
        f"Bonjou,\n\nBiznis « {org.name} » la fèmen sou KONMBIT pa {user.full_name or user.email}. "
        f"Pèsonn pa ka konekte ankò. Tout done yo ap efase nèt nan {CLOSURE_GRACE_DAYS} jou.\n"
        "Si se yon erè, ekri kontak@konmbit.com touswit.\n\n"
        f"L'entreprise « {org.name} » a été fermée sur KONMBIT. Plus personne ne peut se connecter. "
        f"Toutes les données seront supprimées définitivement dans {CLOSURE_GRACE_DAYS} jours. "
        "En cas d'erreur, écrivez immédiatement à kontak@konmbit.com.\n\n— KONMBIT"
    )
    for admin in admins:
        background.add_task(send_email, admin.email, "KONMBIT — Biznis la fèmen / Entreprise fermée", text)

    return Message(detail="Biznis la fèmen. Tout done li ap efase nèt nan 30 jou.")
