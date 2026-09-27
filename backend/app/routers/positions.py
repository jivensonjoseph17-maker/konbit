"""
Konbit — Router Pozisyon (tit travay)
Chemen: backend/app/routers/positions.py

Endpoint yo:
    GET    /api/positions            Lis pozisyon biznis la (tout moun konekte)
    POST   /api/positions            Kreye yon pozisyon (HR)
    PATCH  /api/positions/{id}       Chanje non, Direksyon, aktif (HR)
    DELETE /api/positions/{id}       Efase yon pozisyon PESONN pa janm okipe (HR)
    POST   /api/positions/defaults   Ajoute lis pa defo a (HR) — pa kreye doub

Yon pozisyon "Direksyon" (is_leadership) parèt anlè òganigram lan. Sa PA
bay moun nan okenn dwa nan sistèm lan: dwa yo soti nan wòl kont lan.
Chak nouvo biznis resevwa DEFAULT_POSITIONS lè l enskri (gade auth.signup).

Yon pozisyon yon moun te okipe pa efase: nou dezaktive l, pou dosye
ansyen anplwaye yo kenbe tit yo.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import Employee, JobPosting, Position
from ..schemas import Message, PositionCreate, PositionOut, PositionUpdate

router = APIRouter()

# (tit, pati Direksyon). Tit yo an kreyòl: biznis la ka chanje yo.
DEFAULT_POSITIONS: list[tuple[str, bool]] = [
    ("Pwopriyetè", True),
    ("Fondatè", True),
    ("Kofondatè", True),
    ("Direktè jeneral", True),
    ("Direktè finans", True),
    ("Direktè resous imèn", True),
    ("Manadjè", False),
    ("Sipèvizè", False),
    ("Kontab", False),
    ("Kesye", False),
    ("Sekretè", False),
    ("Anplwaye", False),
]


def _key(title: str) -> str:
    """Konparezon san diferans majiskil/espas: 'kesye ' == 'Kesye'."""
    return " ".join((title or "").split()).casefold()


def seed_default_positions(db: Session, org_id: int) -> int:
    """
    Ajoute pozisyon pa defo yo ki poko egziste. Retounen konbyen ki kreye.
    Pa komite: moun ki rele l la deside (signup komite tout ansanm).
    """
    existing = {
        _key(t) for (t,) in db.query(Position.title).filter(Position.organization_id == org_id).all()
    }
    created = 0
    for title, leadership in DEFAULT_POSITIONS:
        if _key(title) in existing:
            continue
        db.add(Position(organization_id=org_id, title=title, is_leadership=leadership, is_active=True))
        existing.add(_key(title))
        created += 1
    return created


def _get_or_404(db: Session, org_id: int, position_id: int) -> Position:
    pos = db.query(Position).filter(
        Position.id == position_id,
        Position.organization_id == org_id,
    ).first()
    if pos is None:
        raise HTTPException(status_code=404, detail="Pozisyon an pa jwenn.")
    return pos


def _title_taken(db: Session, org_id: int, title: str, exclude_id: Optional[int] = None) -> bool:
    wanted = _key(title)
    rows = db.query(Position.id, Position.title).filter(Position.organization_id == org_id).all()
    return any(_key(t) == wanted and pid != exclude_id for pid, t in rows)


def _counts(db: Session, org_id: int) -> dict[int, int]:
    """Konbyen anplwaye AKTIF okipe chak pozisyon — yon sèl rekèt."""
    rows = db.query(Employee.position_id, func.count(Employee.id)).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
        Employee.position_id.isnot(None),
    ).group_by(Employee.position_id).all()
    return {pid: n for pid, n in rows}


def _out(pos: Position, count: int) -> PositionOut:
    out = PositionOut.model_validate(pos)
    out.employee_count = count
    return out


# ---------------------------------------------------------------------------
# LIS
# ---------------------------------------------------------------------------

class PositionList(BaseModel):
    total: int
    items: list[PositionOut]


@router.get("", response_model=PositionList)
def list_positions(
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
    include_inactive: Annotated[bool, Query()] = False,
):
    """Tit yo pa sansib: tout moun konekte ka wè yo (òganigram, fòm)."""
    q = db.query(Position).filter(Position.organization_id == org_id)
    if not include_inactive:
        q = q.filter(Position.is_active.is_(True))
    items = q.order_by(Position.is_leadership.desc(), Position.title).all()
    counts = _counts(db, org_id)
    return PositionList(total=len(items), items=[_out(p, counts.get(p.id, 0)) for p in items])


# ---------------------------------------------------------------------------
# KREYE / MODIFYE / EFASE
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_hr)],
)
def create_position(payload: PositionCreate, org_id: TenantId, db: DbSession):
    title = " ".join(payload.title.split())
    if _title_taken(db, org_id, title):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Yon pozisyon ak non sa a deja egziste.")
    data = payload.model_dump()
    data["title"] = title
    pos = Position(organization_id=org_id, is_active=True, **data)
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return _out(pos, 0)


@router.post("/defaults", response_model=None, dependencies=[Depends(require_hr)])
def add_default_positions(org_id: TenantId, db: DbSession) -> dict:
    """Pou biznis ki te enskri anvan lis pa defo a te egziste. DWE rete anvan /{id}."""
    created = seed_default_positions(db, org_id)
    db.commit()
    return {"created": created}


@router.patch("/{position_id}", response_model=PositionOut, dependencies=[Depends(require_hr)])
def update_position(position_id: int, payload: PositionUpdate, org_id: TenantId, db: DbSession):
    pos = _get_or_404(db, org_id, position_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("title") is not None:
        data["title"] = " ".join(data["title"].split())
        if _title_taken(db, org_id, data["title"], exclude_id=pos.id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Yon pozisyon ak non sa a deja egziste.")

    for field, value in data.items():
        if value is None and field in ("title", "is_leadership", "is_active"):
            continue            # kolòn sa yo pa aksepte NULL
        setattr(pos, field, value)

    db.commit()
    db.refresh(pos)
    return _out(pos, _counts(db, org_id).get(pos.id, 0))


@router.delete("/{position_id}", response_model=Message, dependencies=[Depends(require_hr)])
def delete_position(position_id: int, org_id: TenantId, db: DbSession):
    pos = _get_or_404(db, org_id, position_id)
    used = db.query(Employee.id).filter(
        Employee.organization_id == org_id,
        Employee.position_id == pos.id,          # menm ansyen anplwaye yo
    ).first() or db.query(JobPosting.id).filter(
        JobPosting.organization_id == org_id,
        JobPosting.position_id == pos.id,
    ).first()
    if used:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Pozisyon sa a gen moun ki okipe l. Dezaktive l pito.")
    db.delete(pos)
    db.commit()
    return Message(detail="Pozisyon an efase.")