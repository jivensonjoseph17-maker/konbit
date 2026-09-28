"""
Konbit — Router Jounal odit
Chemen: backend/app/routers/audit.py

    GET /api/audit           Lis aksyon yo (filtè + paginasyon), pi resan an premye
    GET /api/audit/filters   Valè pou lis dewoulan yo (aksyon, kalite, moun)
    GET /api/audit/export    Menm filtè yo an CSV (maks EXPORT_LIMIT liy).
                             Ekspòtasyon an li menm ale nan jounal la.

ADMINISTRATÈ biznis la sèlman (require_admin). Chak rekèt filtre sou
organization_id ki soti nan token an: yon biznis pa janm wè jounal yon lòt.

Dat yo (date_from / date_to) se jou LOKAL biznis la (fizo orè nan Paramèt
biznis), pa jou UTC. Si date_from pi ta pase date_to, nou jis ranvèse yo.
"""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import and_, or_

from ..deps import CurrentUser, DbSession, TenantId, require_admin
from ..models import AuditLog, Organization, User
from ..timezone_utils import get_local_today

router = APIRouter()

DEFAULT_TZ = "America/Port-au-Prince"
EXPORT_LIMIT = 5000

# Aksyon ki parèt an WOUJ: lajan, modpas, wòl, done sansib, tablèt pwentaj.
SENSITIVE_ACTIONS = frozenset({
    "adjust",              # fich peye ajiste
    "change_role",
    "reset_password",
    "view_sensitive",      # NIF / nimewo kont labank
    "kiosk_pin_set",
    "kiosk_pin_lock",
    "kiosk_device_lock",
    "activate",            # tablèt aktive
    "revoke",              # tablèt dezaktive
})
BANK_EXPORT_PREFIX = "Rapò bank"   # payroll_exports: changes=f"Rapò {kind}: …"


def is_sensitive(action: str, entity_type: str, changes: Optional[str]) -> bool:
    if action in SENSITIVE_ACTIONS:
        return True
    if action == "export":
        # Fichye bank lan gen nimewo kont yo; jounal odit la gen tout istwa a.
        return entity_type == "audit_log" or (changes or "").startswith(BANK_EXPORT_PREFIX)
    return False


def _sensitive_clause():
    """Menm règ ak is_sensitive(), men an SQL pou filtè a."""
    return or_(
        AuditLog.action.in_(SENSITIVE_ACTIONS),
        and_(
            AuditLog.action == "export",
            or_(
                AuditLog.entity_type == "audit_log",
                AuditLog.changes.like(BANK_EXPORT_PREFIX + "%"),
            ),
        ),
    )


def safe_cell(value) -> str:
    """
    Yon selil CSV ki kòmanse ak = + - @ ta ka egzekite kòm fòmil nan Excel.
    Detay yo ka gen tèks yon moun tape (non biznis, nòt): nou mete ' devan.
    """
    if value is None:
        return ""
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


# ---------------------------------------------------------------------------
# FIZO ORÈ AK DAT
# ---------------------------------------------------------------------------

def _zone(db, org_id: int) -> ZoneInfo:
    org = db.get(Organization, org_id)
    name = getattr(org, "timezone", None) or DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def _as_utc(value: datetime) -> datetime:
    """SQLite retounen dat san fizo orè: se UTC (CURRENT_TIMESTAMP)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utc_start_of(day: date, zone: ZoneInfo) -> datetime:
    """Minwi LOKAL jou a, an UTC."""
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ---------------------------------------------------------------------------
# FILTÈ YO (menm pou lis la ak CSV a)
# ---------------------------------------------------------------------------

class AuditFilters:
    def __init__(
        self,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        user_id: Optional[int] = None,
        action: Annotated[Optional[str], Query(max_length=100)] = None,
        entity_type: Annotated[Optional[str], Query(max_length=100)] = None,
        q: Annotated[Optional[str], Query(max_length=100)] = None,
        sensitive_only: bool = False,
    ):
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        self.date_from = date_from
        self.date_to = date_to
        self.user_id = user_id
        self.action = (action or "").strip() or None
        self.entity_type = (entity_type or "").strip() or None
        self.q = (q or "").strip() or None
        self.sensitive_only = sensitive_only


FiltersDep = Annotated[AuditFilters, Depends()]


def _query(db, org_id: int, f: AuditFilters, zone: ZoneInfo):
    query = (
        db.query(AuditLog, User)
        .outerjoin(User, User.id == AuditLog.user_id)
        .filter(AuditLog.organization_id == org_id)
    )
    if f.date_from:
        query = query.filter(AuditLog.created_at >= _utc_start_of(f.date_from, zone))
    if f.date_to:
        query = query.filter(
            AuditLog.created_at < _utc_start_of(f.date_to + timedelta(days=1), zone)
        )
    if f.user_id:
        query = query.filter(AuditLog.user_id == f.user_id)
    if f.action:
        query = query.filter(AuditLog.action == f.action)
    if f.entity_type:
        query = query.filter(AuditLog.entity_type == f.entity_type)
    if f.sensitive_only:
        query = query.filter(_sensitive_clause())
    if f.q:
        pattern = f"%{_escape_like(f.q)}%"
        query = query.filter(or_(
            AuditLog.changes.ilike(pattern, escape="\\"),
            AuditLog.action.ilike(pattern, escape="\\"),
            AuditLog.entity_type.ilike(pattern, escape="\\"),
            AuditLog.ip_address.ilike(pattern, escape="\\"),
            User.full_name.ilike(pattern, escape="\\"),
            User.email.ilike(pattern, escape="\\"),
        ))
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


# ---------------------------------------------------------------------------
# REPONS YO
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    id: int
    at: datetime                     # UTC
    local_date: str                  # "2026-09-27" — jou LOKAL biznis la
    local_time: str                  # "21:45"
    user_id: Optional[int] = None    # None = tablèt pwentaj oswa sistèm
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[int] = None
    changes: Optional[str] = None
    ip_address: Optional[str] = None
    sensitive: bool


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    page: int
    size: int


class AuditUser(BaseModel):
    id: int
    name: str


class AuditFilterValues(BaseModel):
    actions: list[str]
    entity_types: list[str]
    users: list[AuditUser]


def _entry(log: AuditLog, user: Optional[User], zone: ZoneInfo) -> AuditEntry:
    at = _as_utc(log.created_at)
    local = at.astimezone(zone)
    return AuditEntry(
        id=log.id,
        at=at,
        local_date=local.strftime("%Y-%m-%d"),
        local_time=local.strftime("%H:%M"),
        user_id=log.user_id,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        changes=log.changes,
        ip_address=log.ip_address,
        sensitive=is_sensitive(log.action, log.entity_type, log.changes),
    )


# ---------------------------------------------------------------------------
# ENDPOINT YO
# ---------------------------------------------------------------------------

@router.get("", response_model=AuditPage, dependencies=[Depends(require_admin)])
def list_audit(
    f: FiltersDep,
    org_id: TenantId,
    db: DbSession,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    zone = _zone(db, org_id)
    query = _query(db, org_id, f, zone)
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return AuditPage(
        items=[_entry(log, user, zone) for log, user in rows],
        total=total, page=page, size=size,
    )


@router.get("/filters", response_model=AuditFilterValues, dependencies=[Depends(require_admin)])
def audit_filter_values(org_id: TenantId, db: DbSession):
    """Sèlman valè ki egziste nan jounal PWÒP biznis la."""
    mine = AuditLog.organization_id == org_id
    actions = [a for (a,) in db.query(AuditLog.action).filter(mine)
               .distinct().order_by(AuditLog.action).all()]
    entity_types = [e for (e,) in db.query(AuditLog.entity_type).filter(mine)
                    .distinct().order_by(AuditLog.entity_type).all()]
    users = (
        db.query(User.id, User.full_name)
        .join(AuditLog, AuditLog.user_id == User.id)
        .filter(mine, User.organization_id == org_id)
        .distinct()
        .order_by(User.full_name)
        .all()
    )
    return AuditFilterValues(
        actions=actions,
        entity_types=entity_types,
        users=[AuditUser(id=uid, name=name) for uid, name in users],
    )


CSV_HEADER = ["Dat", "Lè", "Moun", "Imel", "Aksyon", "Kalite", "ID", "Detay", "Adrès IP", "Sansib"]


@router.get("/export", dependencies=[Depends(require_admin)])
def export_audit(
    f: FiltersDep,
    user: CurrentUser,
    org_id: TenantId,
    request: Request,
    db: DbSession,
):
    zone = _zone(db, org_id)
    rows = _query(db, org_id, f, zone).limit(EXPORT_LIMIT).all()

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for log, who in rows:
        e = _entry(log, who, zone)
        writer.writerow([safe_cell(v) for v in (
            e.local_date, e.local_time, e.user_name or "", e.user_email or "",
            e.action, e.entity_type, e.entity_id, e.changes, e.ip_address,
            "wi" if e.sensitive else "",
        )])

    # Kiyès ki telechaje tout istwa a — sa li menm se yon aksyon sansib.
    db.add(AuditLog(
        organization_id=org_id, user_id=user.id, action="export", entity_type="audit_log",
        entity_id=None, changes=f"Jounal odit CSV: {len(rows)} liy.",
        ip_address=request.client.host if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    db.commit()

    org = db.get(Organization, org_id)
    slug = "".join(c for c in (org.slug if org else "biznis") if c.isalnum() or c == "-")
    filename = f"jounal-odit-{slug}-{get_local_today(db, org_id):%Y-%m-%d}.csv"
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store"},
    )