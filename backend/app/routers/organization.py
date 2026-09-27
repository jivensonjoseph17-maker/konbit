"""
Konbit — Router Paramèt biznis
Chemen: backend/app/routers/organization.py

    GET   /api/organization      Paramèt biznis la (HR ak admin ka li yo)
    PATCH /api/organization      Chanje yo (ADMIN sèlman) — chak chanjman ale nan jounal odit la

Mòd pwentaj la chanje nan /api/kiosk/settings (menm jounal odit, menm règ).
Slug la (lyen paj karyè a) PA chanje isit: lyen ki deja pataje yo ta kase.
"""

from typing import Annotated, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

from ..clock_mode import get_clock_mode
from ..deps import CurrentUser, DbSession, TenantId, require_admin, require_hr
from ..models import AuditLog, Currency, Organization
from ..schemas import HttpUrlStr

router = APIRouter()

PayFrequency = Literal["weekly", "biweekly", "semimonthly", "monthly"]


def _valid_timezone(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Fizo orè sa a pa valab.")
    return v


class OrganizationSettings(BaseModel):
    model_config = {"from_attributes": True}
    name: str
    slug: str
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    default_currency: Currency
    timezone: Optional[str] = None
    pay_frequency: str
    clock_mode: str = "phone"


class OrganizationSettingsUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=200)
    legal_name: Optional[str] = Field(default=None, max_length=200)
    tax_id: Optional[str] = Field(default=None, max_length=50)
    industry: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=500)
    city: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[EmailStr] = None
    logo_url: Optional[HttpUrlStr] = None
    default_currency: Optional[Currency] = None
    timezone: Annotated[Optional[str], AfterValidator(_valid_timezone)] = None
    pay_frequency: Optional[PayFrequency] = None

    @field_validator("name", "legal_name", "tax_id", "industry", "address", "city", "phone")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


# Chan ki pa ka vid (kolòn NOT NULL oswa enpòtan): yon `null` pa chanje yo.
_REQUIRED = {"name", "default_currency", "timezone", "pay_frequency"}


def _settings(db, org: Organization) -> OrganizationSettings:
    out = OrganizationSettings.model_validate(org)
    out.clock_mode = get_clock_mode(db, org.id)
    return out


def _get_org(db, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Òganizasyon an pa jwenn.")
    return org


@router.get("", response_model=OrganizationSettings, dependencies=[Depends(require_hr)])
def read_settings(org_id: TenantId, db: DbSession):
    return _settings(db, _get_org(db, org_id))


@router.patch("", response_model=OrganizationSettings, dependencies=[Depends(require_admin)])
def update_settings(payload: OrganizationSettingsUpdate, user: CurrentUser, org_id: TenantId,
                    request: Request, db: DbSession):
    org = _get_org(db, org_id)
    data = payload.model_dump(exclude_unset=True)

    changes = []
    for field, value in data.items():
        if value is None and field in _REQUIRED:
            continue
        if isinstance(value, str) and value == "" and field not in _REQUIRED:
            value = None
        before = getattr(org, field)
        before_cmp = getattr(before, "value", before)
        after_cmp = getattr(value, "value", value)
        if before_cmp == after_cmp:
            continue
        setattr(org, field, value)
        changes.append(f"{field}: {before_cmp!r} -> {after_cmp!r}")

    if changes:
        db.add(AuditLog(
            organization_id=org_id, user_id=user.id, action="update",
            entity_type="organization_settings", entity_id=org_id,
            changes="; ".join(changes)[:4000],
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
    db.commit()
    db.refresh(org)
    return _settings(db, org)