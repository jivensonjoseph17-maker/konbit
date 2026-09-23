"""
Konbit — Fizo orè biznis la
Chemen: backend/app/timezone_utils.py

TOUT kalkil ki mande konnen "ki jou nou ye kounye a" (demann konje ki nan
tan pase, fòmasyon an reta, ane pa defo pou balans konje, kiyès ki la
jodi a...) dwe pase pa isit la — pa `date.today()` oswa `datetime.now()`
san fizo orè, ki bay lè SÈVÈ a (souvan UTC), pa lè biznis la an Ayiti.

San sa, yon evènman ki rive apre 8è diswa an Ayiti (minwit UTC) ta
kalkile sou move jou a — yon demann konje ta sanble li "nan tan pase"
plizyè èdtan twò bonè, pa egzanp.

Sa a se menm lojik ki te deja nan attendance.py — nou mete l isit yon
sèl fwa pou leaves.py ak training.py ka sèvi avè l tou, san repetisyon.
"""

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from .models import Organization

logger = logging.getLogger("konbit")

DEFAULT_TZ = "America/Port-au-Prince"


def _utc_available() -> bool:
    try:
        ZoneInfo("UTC")
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def get_org_timezone(db: Session, org_id: int):
    """
    Fizo orè biznis la, ak yon chèn sekou: fizo orè òganizasyon an,
    epi si sa pa disponib, fizo orè Ayiti pa defo.
    """
    name = db.query(Organization.timezone).filter(Organization.id == org_id).scalar()
    for candidate in (name, DEFAULT_TZ):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue

    # Baz done fizo orè a pa disponib ditou (sou Windows: `pip install tzdata`).
    # Nou tonbe sou UTC olye nou kraze paj la — men nou di l fò nan lòg yo,
    # paske dat yo ap fo apre 8è diswa lè Ayiti.
    logger.error(
        "Fizo orè '%s' pa jwenn. Enstale pakè 'tzdata'. N ap sèvi ak UTC pou kounye a.",
        name or DEFAULT_TZ,
    )
    return ZoneInfo("UTC") if _utc_available() else timezone.utc


def get_local_today(db: Session, org_id: int) -> date:
    """Dat jodi a, nan lè LOKAL biznis la — pa dat sèvè a."""
    return datetime.now(get_org_timezone(db, org_id)).date()