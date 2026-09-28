"""
Konbit — Logo biznis la (fichye)
Chemen: backend/app/routers/org_logo.py

    GET    /api/organization/logo    Enfòmasyon sou fichye logo a (HR ak admin)
    PUT    /api/organization/logo    Telechaje yon logo (ADMIN) — JSON {"data_base64": "..."}
    DELETE /api/organization/logo    Retire l (ADMIN)
    GET    /api/logos/{org_slug}     Imaj la (PIBLIK: paj karyè, ba anlè, <img>)

POUKISA NOU SERE FICHYE A NAN BAZ DONE A olye nou li yon lyen:
PDF fich peye a fèt sou sèvè a. Si sèvè a te al chèche yon lyen yon admin
tape, yon moun ta ka mete yon adrès ENTÈN (egz: http://169.254.169.254/…)
epi fè sèvè a li done prive (atak SSRF). Avèk yon fichye, sèvè a pa janm
ale sou entènèt.

NETWAYAJ: nou pa janm sere fichye a jan li rive. Pillow ouvri l, verifye se
vrèman yon PNG/JPG/WEBP, vire l dwat (EXIF), retire tout metadone (GPS
telefòn nan…), redui l a 512 px maksimòm, epi re-anrejistre l an PNG.
Yon fichye ki fè kòmsi li se yon imaj men ki gen lòt bagay ladan l pa pase.

Lyen logo a (organizations.logo_url) toujou mache: fichye a pase DEVAN li.
"""

import base64
import binascii
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_admin, require_hr
from ..models import AuditLog, Organization, OrganizationLogo

logger = logging.getLogger("konbit")

router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024       # fichye moun nan voye a
MAX_PIXELS = 36_000_000                  # 6000 × 6000: pwoteksyon kont "bonm" dekonpresyon
MIN_SIDE = 16
MAX_SIDE = 512                           # sa nou sere a
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


# ---------------------------------------------------------------------------
# ZOUTI POU LÒT ROUTER YO (auth, jobs, payroll)
# ---------------------------------------------------------------------------

def logo_url_for(db: Session, org: Organization) -> Optional[str]:
    """
    Lyen logo biznis la pou frontend lan. Fichye a an premye:
    "/api/logos/<slug>?v=<hash>" (frontend lan mete adrès API a devan).
    `v` chanje chak fwa logo a chanje, kidonk navigatè a pa kenbe ansyen an.
    Si pa gen fichye: lyen https ki nan Paramèt biznis la (oswa None).
    """
    row = db.query(OrganizationLogo.sha256).filter(
        OrganizationLogo.organization_id == org.id,
    ).first()
    if row:
        return f"/api/logos/{org.slug}?v={row[0][:12]}"
    return org.logo_url


def logo_png_for(db: Session, org_id: int) -> Optional[bytes]:
    """PNG netwaye a pou PDF fich peye a, oswa None."""
    row = db.query(OrganizationLogo.data).filter(
        OrganizationLogo.organization_id == org_id,
    ).first()
    return bytes(row[0]) if row else None


# ---------------------------------------------------------------------------
# NETWAYAJ IMAJ LA
# ---------------------------------------------------------------------------

def _looks_like_image(raw: bytes) -> bool:
    """Premye bytes yo (siyati) — anvan menm nou bay Pillow fichye a."""
    return (
        raw.startswith(b"\x89PNG\r\n\x1a\n")
        or raw.startswith(b"\xff\xd8\xff")
        or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    )


def normalize_logo(raw: bytes) -> tuple[bytes, int, int]:
    """Retounen (png, lajè, wotè). Voye HTTPException 422 si imaj la pa bon."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="Imaj la twò gwo. Maksimòm 2 Mo.")
    if not _looks_like_image(raw):
        raise HTTPException(status_code=422, detail="Chwazi yon imaj PNG, JPG oswa WEBP.")

    # 1. Li sèlman tèt fichye a (gwosè a) anvan nou dekonprese anyen.
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format
            width, height = probe.size
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Nou pa ka li imaj sa a. Eseye yon lòt fichye.")

    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(status_code=422, detail="Chwazi yon imaj PNG, JPG oswa WEBP.")
    if width * height > MAX_PIXELS:
        raise HTTPException(status_code=422, detail="Imaj la twò gwo an piksèl. Maksimòm 6000 × 6000.")
    if width < MIN_SIDE or height < MIN_SIDE:
        raise HTTPException(status_code=422,
                            detail="Imaj la twò piti. Li dwe gen omwen 16 piksèl chak bò.")

    # 2. Dekonprese, vire l dwat, retire metadone, redui, re-anrejistre an PNG.
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            clean = ImageOps.exif_transpose(img).convert("RGBA")
        clean.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        clean.save(out, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Nou pa ka li imaj sa a. Eseye yon lòt fichye.")

    return out.getvalue(), clean.width, clean.height


# ---------------------------------------------------------------------------
# ENDPOINT YO
# ---------------------------------------------------------------------------

class LogoUpload(BaseModel):
    # 2 Mo an base64 ≈ 2,8 milyon karaktè (+ ti marj pou "data:image/png;base64,")
    data_base64: str = Field(min_length=8, max_length=2_900_000)


class LogoInfo(BaseModel):
    has_file: bool
    url: Optional[str] = None           # "/api/logos/<slug>?v=…" (relatif ak API a)
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    updated_at: Optional[datetime] = None


def _info(db: Session, org: Organization) -> LogoInfo:
    row = db.query(OrganizationLogo).filter(OrganizationLogo.organization_id == org.id).first()
    if row is None:
        return LogoInfo(has_file=False)
    return LogoInfo(
        has_file=True, url=f"/api/logos/{org.slug}?v={row.sha256[:12]}",
        width=row.width, height=row.height, size_bytes=len(row.data),
        updated_at=row.updated_at,
    )


def _org(db: Session, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Òganizasyon an pa jwenn.")
    return org


def _audit(db: Session, request: Request, org_id: int, user_id: int,
           action: str, changes: str) -> None:
    db.add(AuditLog(
        organization_id=org_id, user_id=user_id, action=action,
        entity_type="organization_logo", entity_id=org_id, changes=changes,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))


@router.get("/api/organization/logo", response_model=LogoInfo,
            dependencies=[Depends(require_hr)])
def read_logo_info(org_id: TenantId, db: DbSession):
    return _info(db, _org(db, org_id))


@router.put("/api/organization/logo", response_model=LogoInfo,
            dependencies=[Depends(require_admin)])
def upload_logo(payload: LogoUpload, user: CurrentUser, org_id: TenantId,
                request: Request, db: DbSession):
    text = payload.data_base64.strip()
    if text.startswith("data:") and "," in text:      # "data:image/png;base64,AAAA…"
        text = text.split(",", 1)[1]
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Nou pa ka li imaj sa a. Eseye yon lòt fichye.")

    png, width, height = normalize_logo(raw)
    digest = hashlib.sha256(png).hexdigest()
    org = _org(db, org_id)

    row = db.query(OrganizationLogo).filter(OrganizationLogo.organization_id == org_id).first()
    if row is None:
        row = OrganizationLogo(organization_id=org_id)
        db.add(row)
    row.data = png
    row.content_type = "image/png"
    row.sha256 = digest
    row.width = width
    row.height = height
    row.updated_by_id = user.id
    row.updated_at = datetime.now(timezone.utc)

    _audit(db, request, org_id, user.id, "update",
           f"Logo telechaje: {width}×{height} px, {len(png) // 1024} Ko "
           f"(fichye orijinal: {len(raw) // 1024} Ko).")
    db.commit()
    return _info(db, org)


@router.delete("/api/organization/logo", response_model=LogoInfo,
               dependencies=[Depends(require_admin)])
def delete_logo(user: CurrentUser, org_id: TenantId, request: Request, db: DbSession):
    org = _org(db, org_id)
    row = db.query(OrganizationLogo).filter(OrganizationLogo.organization_id == org_id).first()
    if row is not None:
        db.delete(row)
        _audit(db, request, org_id, user.id, "delete", "Logo retire.")
        db.commit()
    return _info(db, org)


@router.get("/api/logos/{org_slug}", tags=["Piblik"])
def public_logo(org_slug: str, request: Request, db: DbSession):
    """
    Imaj logo a, san koneksyon: paj karyè a piblik, e yon <img> pa ka voye token.
    Se yon PNG NOU MENM te kreye (normalize_logo), pa fichye moun nan te voye a.
    """
    row = (
        db.query(OrganizationLogo)
        .join(Organization, Organization.id == OrganizationLogo.organization_id)
        .filter(Organization.slug == org_slug.lower().strip(), Organization.is_active.is_(True))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sa ou chèche a pa egziste.")

    etag = f'"{row.sha256[:32]}"'
    # ?v=<hash> nan lyen an: kontni an pa janm chanje pou lyen sa a.
    cache = ("public, max-age=31536000, immutable" if request.query_params.get("v")
             else "public, max-age=300")
    headers = {
        "ETag": etag,
        "Cache-Control": cache,
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        # Frontend lan (lòt domèn) dwe ka afiche l nan yon <img>.
        "Cross-Origin-Resource-Policy": "cross-origin",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=bytes(row.data), media_type="image/png", headers=headers)