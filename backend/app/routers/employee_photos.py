"""
Konbit — Foto pwofil anplwaye
Chemen: backend/app/routers/employee_photos.py

    PUT    /api/profile/photo              Mete / chanje foto mwen  ({"data_base64": ...})
    DELETE /api/profile/photo              Retire foto mwen
    DELETE /api/employees/{id}/photo       HR retire foto yon moun (foto ki pa apwopriye)
    GET    /api/photos/map                 {employee_id: lyen} pou tout biznis la (moun ki konekte)
    GET    /api/photos/{kle}.jpg           Imaj la (<img> pa ka voye token)

NETWAYAJ: menm jan ak logo a (org_logo.py) — Pillow verifye se vrèman yon
PNG/JPG/WEBP, vire l dwat, retire metadone (GPS telefòn nan!), KOUPE L KARE
(santre yon ti jan pi wo pou figi a) epi re-anrejistre l an JPEG 256 px.

LYEN AN: chak foto gen yon kle aleyatwa (24 karaktè) ki chanje chak fwa moun
nan chanje foto l. Pa gen nimewo anplwaye nan lyen an: pèsonn pa ka devine
foto yon lòt moun, e yon ansyen foto pa ka rale ankò apre li chanje.
"""

import base64
import binascii
import hashlib
import io
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import CurrentEmployee, CurrentUser, DbSession, TenantId, require_hr
from ..models import AuditLog, Employee, EmployeePhoto
from .org_logo import ALLOWED_FORMATS, MAX_PIXELS, MAX_UPLOAD_BYTES, MIN_SIDE, _looks_like_image

router = APIRouter()

PHOTO_SIDE = 256
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,40}$")


# ---------------------------------------------------------------------------
# ZOUTI POU LÒT ROUTER YO
# ---------------------------------------------------------------------------

def photo_url_for(db: Session, employee_id: Optional[int]) -> Optional[str]:
    """"/api/photos/<kle>.jpg" (relatif ak API a), oswa None."""
    if not employee_id:
        return None
    row = db.query(EmployeePhoto.public_key).filter(EmployeePhoto.employee_id == employee_id).first()
    return f"/api/photos/{row[0]}.jpg" if row else None


def normalize_photo(raw: bytes) -> bytes:
    """JPEG kare 256 px, san metadone. HTTPException 422 si imaj la pa bon."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=422, detail="Imaj la twò gwo. Maksimòm 2 Mo.")
    if not _looks_like_image(raw):
        raise HTTPException(status_code=422, detail="Chwazi yon imaj PNG, JPG oswa WEBP.")
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
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            upright = ImageOps.exif_transpose(img)
            if upright.mode in ("RGBA", "LA", "P"):
                # Fon blan pou foto ki gen transparans (JPEG pa konn transparans).
                rgba = upright.convert("RGBA")
                base = Image.new("RGB", rgba.size, (255, 255, 255))
                base.paste(rgba, mask=rgba.split()[-1])
                upright = base
            square = ImageOps.fit(upright.convert("RGB"), (PHOTO_SIDE, PHOTO_SIDE),
                                  Image.Resampling.LANCZOS, centering=(0.5, 0.4))
        out = io.BytesIO()
        square.save(out, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Nou pa ka li imaj sa a. Eseye yon lòt fichye.")
    return out.getvalue()


def _decode(text: str) -> bytes:
    text = text.strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="Nou pa ka li imaj sa a. Eseye yon lòt fichye.")


def _audit(db: Session, request: Request, org_id: int, user_id: int, action: str,
           employee_id: int, changes: str) -> None:
    db.add(AuditLog(
        organization_id=org_id, user_id=user_id, action=action, entity_type="employee_photo",
        entity_id=employee_id, changes=changes,
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))


# ---------------------------------------------------------------------------
# ANPLWAYE A
# ---------------------------------------------------------------------------

class PhotoUpload(BaseModel):
    data_base64: str = Field(min_length=8, max_length=2_900_000)


class PhotoOut(BaseModel):
    url: Optional[str] = None


@router.put("/api/profile/photo", response_model=PhotoOut)
def upload_my_photo(payload: PhotoUpload, emp: CurrentEmployee, user: CurrentUser,
                    org_id: TenantId, request: Request, db: DbSession):
    jpeg = normalize_photo(_decode(payload.data_base64))
    row = db.get(EmployeePhoto, emp.id)
    if row is None:
        row = EmployeePhoto(employee_id=emp.id, organization_id=org_id)
        db.add(row)
    row.data = jpeg
    row.sha256 = hashlib.sha256(jpeg).hexdigest()
    row.public_key = secrets.token_urlsafe(18)          # nouvo lyen: ansyen an pa mache ankò
    row.updated_by_id = user.id
    row.updated_at = datetime.now(timezone.utc)
    _audit(db, request, org_id, user.id, "update", emp.id, f"Foto pwofil: {len(jpeg) // 1024} Ko.")
    db.commit()
    return PhotoOut(url=photo_url_for(db, emp.id))


@router.delete("/api/profile/photo", response_model=PhotoOut)
def delete_my_photo(emp: CurrentEmployee, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    row = db.get(EmployeePhoto, emp.id)
    if row is not None:
        db.delete(row)
        _audit(db, request, org_id, user.id, "delete", emp.id, "Foto pwofil retire.")
        db.commit()
    return PhotoOut(url=None)


# ---------------------------------------------------------------------------
# HR
# ---------------------------------------------------------------------------

@router.delete("/api/employees/{employee_id}/photo", response_model=PhotoOut,
               dependencies=[Depends(require_hr)])
def hr_delete_photo(employee_id: int, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    emp = db.query(Employee).filter(
        Employee.id == employee_id, Employee.organization_id == org_id).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    row = db.get(EmployeePhoto, emp.id)
    if row is not None:
        db.delete(row)
        _audit(db, request, org_id, user.id, "delete", emp.id, "Foto pwofil retire pa HR.")
        db.commit()
    return PhotoOut(url=None)


# ---------------------------------------------------------------------------
# LI FOTO YO
# ---------------------------------------------------------------------------

class PhotoMap(BaseModel):
    photos: dict[int, str]


@router.get("/api/photos/map", response_model=PhotoMap)
def photo_map(user: CurrentUser, org_id: TenantId, db: DbSession):
    """Tout moun nan biznis la wè òganigram lan: yo ka wè foto yo tou."""
    rows = db.query(EmployeePhoto.employee_id, EmployeePhoto.public_key).filter(
        EmployeePhoto.organization_id == org_id).all()
    return PhotoMap(photos={eid: f"/api/photos/{key}.jpg" for eid, key in rows})


@router.get("/api/photos/{photo_file}", tags=["Piblik"])
def serve_photo(photo_file: str, db: DbSession):
    key = photo_file[:-4] if photo_file.endswith(".jpg") else ""
    if not KEY_RE.match(key):
        raise HTTPException(status_code=404)
    row = db.query(EmployeePhoto).filter(EmployeePhoto.public_key == key).first()
    if row is None:
        raise HTTPException(status_code=404)
    return Response(content=bytes(row.data), media_type="image/jpeg", headers={
        # Kle a chanje ak chak nouvo foto: kontni yon lyen pa janm chanje.
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
        "Cross-Origin-Resource-Policy": "cross-origin",
    })