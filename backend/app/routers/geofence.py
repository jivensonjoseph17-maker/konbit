"""
Konbit — Zòn otorize (geofence) pou pwentaj sou telefòn
Chemen: backend/app/routers/geofence.py

    GET /api/organization/geofence    Paramèt zòn nan (HR ak admin)
    PUT /api/organization/geofence    Chanje yo (ADMIN)

MÒD:
  off   : pa verifye. Si pozisyon biznis la la, nou kalkile distans lan kanmenm.
  flag  : aksepte pwentaj la, men make antre a `outside_zone` pou HR verifye
          (twò lwen, oswa moun nan pa t pataje pozisyon l).
  block : REFIZE klòk IN si moun nan twò lwen oswa si li pa pataje pozisyon l.
          Klòk OUT pa janm bloke — sinon jounen an ta rete louvri, e HR ta
          gen plis travay. Li make sèlman.

TABLÈT (routers/kiosk.py) pa konsène: tablèt la deja nan biznis la.

LIMIT: yon moun ka fè telefòn li bay yon fo pozisyon. Zòn nan se yon baryè
pou moun ki onèt ak yon siyal pou HR, pa yon prèv. Pou prèv, sèvi ak tablèt la.
"""

import math
from dataclasses import dataclass
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_admin, require_hr
from ..models import AuditLog, Organization

router = APIRouter()

EARTH_RADIUS_M = 6_371_000
MIN_RADIUS_M = 50          # GPS telefòn ka rate 20–50 m anndan yon bilding
MAX_RADIUS_M = 5000

GeofenceMode = Literal["off", "flag", "block"]


# ---------------------------------------------------------------------------
# KALKIL
# ---------------------------------------------------------------------------

def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """Distans ant de pwen sou tè a, an mèt (fòmil haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))))


@dataclass(frozen=True)
class ZoneCheck:
    distance_m: Optional[int]     # None: pa gen pozisyon biznis, oswa moun nan pa pataje pa l
    outside: bool                 # pou `time_entries.outside_zone`


def _center(org: Optional[Organization]):
    if org is None or org.geofence_lat is None or org.geofence_lng is None \
            or not org.geofence_radius_m:
        return None
    return float(org.geofence_lat), float(org.geofence_lng), int(org.geofence_radius_m)


def check_clock_location(db: Session, org_id: int, lat, lng, *, enforce: bool) -> ZoneCheck:
    """
    Verifye pozisyon yon pwentaj sou telefòn.
    `enforce=True` (klòk in): mòd "block" ka voye 403.
    `enforce=False` (klòk out): pa janm refize, make sèlman.
    """
    org = db.get(Organization, org_id)
    center = _center(org)
    if center is None:
        return ZoneCheck(None, False)

    c_lat, c_lng, radius = center
    has_position = lat is not None and lng is not None
    dist = distance_m(float(lat), float(lng), c_lat, c_lng) if has_position else None
    mode = org.geofence_mode or "off"

    if mode == "off":
        return ZoneCheck(dist, False)

    if not has_position:
        if enforce and mode == "block":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pataje pozisyon telefòn ou pou w ka pwente: biznis la mande sa.",
            )
        return ZoneCheck(None, True)

    outside = dist > radius
    if outside and enforce and mode == "block":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ou twò lwen biznis la pou w pwente. Rapwoche w, oswa pale ak manadjè w.",
        )
    return ZoneCheck(dist, outside)


# ---------------------------------------------------------------------------
# PARAMÈT YO
# ---------------------------------------------------------------------------

class GeofenceSettings(BaseModel):
    mode: GeofenceMode = "off"
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_m: Optional[int] = Field(default=None, ge=MIN_RADIUS_M, le=MAX_RADIUS_M)


def _out(org: Organization) -> GeofenceSettings:
    return GeofenceSettings(
        mode=org.geofence_mode or "off",
        latitude=float(org.geofence_lat) if org.geofence_lat is not None else None,
        longitude=float(org.geofence_lng) if org.geofence_lng is not None else None,
        radius_m=org.geofence_radius_m,
    )


def _describe(g: GeofenceSettings) -> str:
    where = f"{g.latitude},{g.longitude}" if g.latitude is not None else "—"
    return f"mòd={g.mode}, pozisyon={where}, distans={g.radius_m or '—'} m"


def _org(db: Session, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Òganizasyon an pa jwenn.")
    return org


@router.get("/api/organization/geofence", response_model=GeofenceSettings,
            dependencies=[Depends(require_hr)])
def read_geofence(org_id: TenantId, db: DbSession):
    return _out(_org(db, org_id))


@router.put("/api/organization/geofence", response_model=GeofenceSettings,
            dependencies=[Depends(require_admin)])
def update_geofence(payload: GeofenceSettings, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    has_lat, has_lng = payload.latitude is not None, payload.longitude is not None
    if has_lat != has_lng or (payload.mode != "off" and not (
            has_lat and has_lng and payload.radius_m)):
        raise HTTPException(
            status_code=422,
            detail="Mete pozisyon biznis la ak yon distans anvan ou aktive zòn nan.",
        )

    org = _org(db, org_id)
    before = _out(org)
    org.geofence_mode = payload.mode
    org.geofence_lat = round(payload.latitude, 7) if has_lat else None
    org.geofence_lng = round(payload.longitude, 7) if has_lng else None
    org.geofence_radius_m = payload.radius_m

    db.add(AuditLog(
        organization_id=org_id, user_id=user.id, action="update",
        entity_type="organization_geofence", entity_id=org_id,
        changes=f"{_describe(before)} -> {_describe(payload)}",
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()
    db.refresh(org)
    return _out(org)