"""
Konbit — Router Òganigram
Chemen: backend/app/routers/hierarchy.py

Endpoint yo:
    GET /api/hierarchy/tree                  Pyebwa konplè biznis la
    GET /api/hierarchy/me/chain              Tout moun ki sou tèt mwen
    GET /api/hierarchy/me/team               Ekip mwen (moun ki anba m)
    GET /api/hierarchy/{id}/chain            Chèn komandman yon anplwaye
    GET /api/hierarchy/{id}/team             Moun ki anba yon anplwaye
    GET /api/hierarchy/{id}/peers            Kòlèg ki gen menm manadjè a
    GET /api/hierarchy/orphans               Moun ki pa gen manadjè (HR)

PÈFÒMANS: nou chaje TOUT anplwaye yo yon sèl fwa nan yon rekèt, epi nou bati
pyebwa a nan memwa. Si nou te fè yon rekèt pa nœud, yon biznis ak 500 moun
t ap bay 500 rekèt SQL.
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import (
    CurrentUser,
    DbSession,
    TenantId,
    ensure_can_view_employee,
    require_hr,
)
from ..models import Department, Employee, Position
from ..schemas import EmployeeBrief, OrgNode

router = APIRouter()

MAX_DEPTH = 20      # gad kont bouk enfini


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

class _Row:
    """Yon anplwaye ak non pozisyon l ak depatman l deja rezoud."""
    __slots__ = ("id", "first_name", "last_name", "employee_number",
                 "photo_url", "manager_id", "position_title", "department_name")

    def __init__(self, emp, position_title, department_name):
        self.id = emp.id
        self.first_name = emp.first_name
        self.last_name = emp.last_name
        self.employee_number = emp.employee_number
        self.photo_url = emp.photo_url
        self.manager_id = emp.manager_id
        self.position_title = position_title
        self.department_name = department_name

    def to_node(self) -> OrgNode:
        return OrgNode(
            id=self.id,
            full_name=f"{self.first_name} {self.last_name}",
            employee_number=self.employee_number,
            position_title=self.position_title,
            department_name=self.department_name,
            photo_url=self.photo_url,
            reports=[],
        )


def _load_rows(db, org_id: int, include_inactive: bool) -> list[_Row]:
    """Yon sèl rekèt ak jwenti sou pozisyon ak depatman."""
    query = (
        db.query(Employee, Position.title, Department.name)
        .outerjoin(Position, Employee.position_id == Position.id)
        .outerjoin(Department, Employee.department_id == Department.id)
        .filter(Employee.organization_id == org_id)
    )
    if not include_inactive:
        query = query.filter(Employee.is_active.is_(True))

    return [_Row(emp, title, dept) for emp, title, dept in query.all()]


def _build_tree(rows: list[_Row], root_id: Optional[int] = None) -> list[OrgNode]:
    """
    Bati pyebwa a nan memwa.
    Si `root_id` bay, nou kòmanse nan moun sa a. Sinon nou kòmanse nan tout
    moun ki pa gen manadjè (rasin yo).
    """
    nodes: dict[int, OrgNode] = {r.id: r.to_node() for r in rows}
    children: dict[Optional[int], list[int]] = {}

    for r in rows:
        children.setdefault(r.manager_id, []).append(r.id)

    def attach(node_id: int, depth: int) -> OrgNode:
        node = nodes[node_id]
        if depth >= MAX_DEPTH:
            return node
        kids = children.get(node_id, [])
        node.reports = [
            attach(k, depth + 1)
            for k in sorted(kids, key=lambda i: (nodes[i].full_name or ""))
        ]
        return node

    if root_id is not None:
        if root_id not in nodes:
            return []
        return [attach(root_id, 0)]

    # Rasin: manager_id vid, OSWA manadjè a pa nan lis la (ex: li enaktif)
    known = set(nodes)
    root_ids = [r.id for r in rows if r.manager_id is None or r.manager_id not in known]
    return [attach(rid, 0) for rid in sorted(root_ids, key=lambda i: nodes[i].full_name or "")]


def _get_employee_or_404(db, org_id: int, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.organization_id == org_id,
    ).first()
    if emp is None:
        raise HTTPException(status_code=404, detail="Anplwaye a pa jwenn.")
    return emp


def _my_employee(db, user) -> Employee:
    emp = db.query(Employee).filter(Employee.user_id == user.id).first()
    if emp is None:
        raise HTTPException(
            status_code=403,
            detail="Kont ou a pa lye ak yon dosye anplwaye.",
        )
    return emp


# ---------------------------------------------------------------------------
# PYEBWA KONPLÈ
# ---------------------------------------------------------------------------

class TreeResponse(BaseModel):
    total_employees: int
    roots: list[OrgNode]


@router.get("/tree", response_model=TreeResponse)
def org_tree(
    org_id: TenantId,
    db: DbSession,
    user: CurrentUser,
    include_inactive: bool = False,
    root_employee_id: Annotated[Optional[int], Query(description="Kòmanse nan yon moun")] = None,
):
    """
    Òganigram konplè biznis la. Tout anplwaye ka wè l — li pa gen done sansib,
    sèlman non, nimewo, pozisyon ak depatman.
    """
    rows = _load_rows(db, org_id, include_inactive)
    if root_employee_id is not None:
        _get_employee_or_404(db, org_id, root_employee_id)
    roots = _build_tree(rows, root_id=root_employee_id)
    return TreeResponse(total_employees=len(rows), roots=roots)


# ---------------------------------------------------------------------------
# CHÈN KOMANDMAN
# ---------------------------------------------------------------------------

class ChainResponse(BaseModel):
    employee: EmployeeBrief
    chain: list[EmployeeBrief]
    depth: int


def _chain_for(db, org_id: int, emp: Employee) -> list[Employee]:
    """Soti nan manadjè dirèk la jouk anwo nèt."""
    chain: list[Employee] = []
    seen: set[int] = {emp.id}
    current_id = emp.manager_id
    depth = 0

    while current_id is not None and depth < MAX_DEPTH:
        if current_id in seen:      # bouk — nou kanpe
            break
        manager = db.query(Employee).filter(
            Employee.id == current_id,
            Employee.organization_id == org_id,
        ).first()
        if manager is None:
            break
        chain.append(manager)
        seen.add(manager.id)
        current_id = manager.manager_id
        depth += 1

    return chain


@router.get("/me/chain", response_model=ChainResponse)
def my_chain(user: CurrentUser, org_id: TenantId, db: DbSession):
    """
    Tout moun ki sou tèt mwen — sa anplwaye a dwe wè.
    Premye nan lis la se manadjè dirèk mwen, dènye a se moun ki pi wo a.
    """
    emp = _my_employee(db, user)
    chain = _chain_for(db, org_id, emp)
    return ChainResponse(
        employee=EmployeeBrief.model_validate(emp),
        chain=[EmployeeBrief.model_validate(m) for m in chain],
        depth=len(chain),
    )


@router.get("/{employee_id}/chain", response_model=ChainResponse)
def employee_chain(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    emp = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, emp, db)
    chain = _chain_for(db, org_id, emp)
    return ChainResponse(
        employee=EmployeeBrief.model_validate(emp),
        chain=[EmployeeBrief.model_validate(m) for m in chain],
        depth=len(chain),
    )


# ---------------------------------------------------------------------------
# EKIP
# ---------------------------------------------------------------------------

class TeamResponse(BaseModel):
    manager: EmployeeBrief
    direct_reports: list[EmployeeBrief]
    total_direct: int
    total_all_levels: int


def _team_for(db, org_id: int, manager: Employee) -> TeamResponse:
    direct = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.manager_id == manager.id,
        Employee.is_active.is_(True),
    ).order_by(Employee.last_name, Employee.first_name).all()

    # Konte tout nivo yo
    collected: set[int] = set()
    frontier = [manager.id]
    depth = 0
    while frontier and depth < MAX_DEPTH:
        rows = db.query(Employee.id).filter(
            Employee.organization_id == org_id,
            Employee.manager_id.in_(frontier),
            Employee.is_active.is_(True),
        ).all()
        nxt = [r[0] for r in rows if r[0] not in collected]
        collected.update(nxt)
        frontier = nxt
        depth += 1

    return TeamResponse(
        manager=EmployeeBrief.model_validate(manager),
        direct_reports=[EmployeeBrief.model_validate(e) for e in direct],
        total_direct=len(direct),
        total_all_levels=len(collected),
    )


@router.get("/me/team", response_model=TeamResponse)
def my_team(user: CurrentUser, org_id: TenantId, db: DbSession):
    emp = _my_employee(db, user)
    return _team_for(db, org_id, emp)


@router.get("/{employee_id}/team", response_model=TeamResponse)
def employee_team(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    emp = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, emp, db)
    return _team_for(db, org_id, emp)


# ---------------------------------------------------------------------------
# KÒLÈG
# ---------------------------------------------------------------------------

class PeersResponse(BaseModel):
    employee: EmployeeBrief
    manager: Optional[EmployeeBrief] = None
    peers: list[EmployeeBrief]


@router.get("/{employee_id}/peers", response_model=PeersResponse)
def employee_peers(
    employee_id: int,
    user: CurrentUser,
    org_id: TenantId,
    db: DbSession,
):
    """Moun ki gen menm manadjè a."""
    emp = _get_employee_or_404(db, org_id, employee_id)
    ensure_can_view_employee(user, emp, db)

    manager = None
    peers = []
    if emp.manager_id is not None:
        manager = db.query(Employee).filter(
            Employee.id == emp.manager_id,
            Employee.organization_id == org_id,
        ).first()
        peers = db.query(Employee).filter(
            Employee.organization_id == org_id,
            Employee.manager_id == emp.manager_id,
            Employee.id != emp.id,
            Employee.is_active.is_(True),
        ).order_by(Employee.last_name).all()

    return PeersResponse(
        employee=EmployeeBrief.model_validate(emp),
        manager=EmployeeBrief.model_validate(manager) if manager else None,
        peers=[EmployeeBrief.model_validate(p) for p in peers],
    )


# ---------------------------------------------------------------------------
# MOUN KI PA GEN MANADJÈ
# ---------------------------------------------------------------------------

class OrphansResponse(BaseModel):
    count: int
    employees: list[EmployeeBrief]
    note: str


@router.get("/orphans", response_model=OrphansResponse, dependencies=[Depends(require_hr)])
def orphan_employees(org_id: TenantId, db: DbSession):
    """
    Anplwaye ki pa gen manadjè. Yon oswa de se nòmal (se patwon an).
    Si ou gen 30, sa vle di òganigram lan pa ranpli — epi apwobasyon konje
    ak evalyasyon p ap gen kote pou yo ale.
    """
    rows = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.manager_id.is_(None),
        Employee.is_active.is_(True),
    ).order_by(Employee.last_name).all()

    return OrphansResponse(
        count=len(rows),
        employees=[EmployeeBrief.model_validate(e) for e in rows],
        note=(
            "Moun sa yo pa gen manadjè. Demann konje yo p ap gen kote pou ale "
            "jouk ou bay yo yon manadjè."
        ),
    )