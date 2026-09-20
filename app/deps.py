"""
Konbit — Depandans FastAPI (otantifikasyon, wòl, izolasyon ant biznis)

SE FICHYE KI PI ENPÒTAN NAN TOUT SISTÈM LAN.

Chak router ki manyen done yon biznis DWE pase pa `get_tenant`. Si ou bliye
l yon sèl fwa sou yon sèl endpoint, biznis A ap ka li fich peye biznis B.
Pa fè filtraj la nan frontend lan — fè l isit.
"""

from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import Employee, Organization, User, UserRole
from .security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Nou pa ka verifye idantite w.",
    headers={"WWW-Authenticate": "Bearer"},
)

FORBIDDEN_ERROR = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Ou pa gen dwa pou aksyon sa a.",
)


# ---------------------------------------------------------------------------
# ITILIZATÈ KOURAN
# ---------------------------------------------------------------------------

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    payload = decode_token(token)
    if payload is None:
        raise CREDENTIALS_ERROR

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def get_current_employee(user: CurrentUser, db: DbSession) -> Employee:
    """Pou endpoint ki mande moun nan se yon anplwaye (clock in, konje, elatriye)."""
    employee = db.query(Employee).filter(
        Employee.user_id == user.id,
        Employee.is_active.is_(True),
    ).first()
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kont ou a pa lye ak yon dosye anplwaye.",
        )
    return employee


CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]


# ---------------------------------------------------------------------------
# IZOLASYON ANT BIZNIS (MULTI-TENANT)
# ---------------------------------------------------------------------------

def get_tenant(user: CurrentUser) -> int:
    """
    Retounen organization_id itilizatè a. Sèvi ak sa a nan CHAK rekèt:

        db.query(Payslip).filter(Payslip.organization_id == org_id, ...)

    Pa janm pran organization_id nan kò rekèt la oswa nan URL la — yon moun
    ta ka chanje l epi li done yon lòt biznis.
    """
    if user.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Super admin dwe chwazi yon òganizasyon esplisitman.",
        )
    if user.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kont ou a pa lye ak okenn òganizasyon.",
        )
    return user.organization_id


TenantId = Annotated[int, Depends(get_tenant)]


def get_organization(org_id: TenantId, db: DbSession) -> Organization:
    org = db.query(Organization).filter(
        Organization.id == org_id,
        Organization.is_active.is_(True),
    ).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Òganizasyon an pa jwenn.")
    return org


# ---------------------------------------------------------------------------
# WÒL
# ---------------------------------------------------------------------------

class RequireRole:
    """
    Sèvi avè l konsa:

        @router.post("/", dependencies=[Depends(RequireRole(UserRole.HR))])
        def create_employee(...): ...

    SUPER_ADMIN pase toupatou.
    """

    def __init__(self, *allowed_roles: UserRole):
        self.allowed = set(allowed_roles)

    def __call__(self, user: CurrentUser) -> User:
        if user.role == UserRole.SUPER_ADMIN:
            return user
        if user.role not in self.allowed:
            raise FORBIDDEN_ERROR
        return user


# Rakoursi ki pi itil yo
require_admin = RequireRole(UserRole.ORG_ADMIN)
require_hr = RequireRole(UserRole.ORG_ADMIN, UserRole.HR)
require_manager = RequireRole(UserRole.ORG_ADMIN, UserRole.HR, UserRole.MANAGER)
require_staff = RequireRole(
    UserRole.ORG_ADMIN, UserRole.HR, UserRole.MANAGER, UserRole.EMPLOYEE
)


# ---------------------------------------------------------------------------
# AKSÈ SOU YON DOSYE ANPLWAYE
# ---------------------------------------------------------------------------

def is_in_management_chain(manager: Employee, subordinate: Employee, max_depth: int = 10) -> bool:
    """Èske `manager` ye kèk kote sou tèt `subordinate`?"""
    current, depth = subordinate.manager, 0
    while current is not None and depth < max_depth:
        if current.id == manager.id:
            return True
        current = current.manager
        depth += 1
    return False


def can_view_employee(viewer: User, target: Employee, db: Session) -> bool:
    """
    Règ aksè sou dosye anplwaye:
      - SUPER_ADMIN, ORG_ADMIN, HR : tout moun nan òganizasyon yo
      - MANAGER : tèt li + tout moun ki anba l
      - EMPLOYEE : tèt li sèlman
    """
    if viewer.role == UserRole.SUPER_ADMIN:
        return True
    if viewer.organization_id != target.organization_id:
        return False
    if viewer.role in (UserRole.ORG_ADMIN, UserRole.HR):
        return True

    viewer_emp = db.query(Employee).filter(Employee.user_id == viewer.id).first()
    if viewer_emp is None:
        return False
    if viewer_emp.id == target.id:
        return True
    if viewer.role == UserRole.MANAGER:
        return is_in_management_chain(viewer_emp, target)
    return False


def ensure_can_view_employee(viewer: User, target: Employee, db: Session) -> None:
    if not can_view_employee(viewer, target, db):
        raise FORBIDDEN_ERROR