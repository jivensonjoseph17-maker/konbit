"""
Konbit — Router Otantifikasyon
Chemen: backend/app/routers/auth.py

Endpoint yo:
    POST  /api/auth/signup            Yon biznis enskri (kreye Organization + ORG_ADMIN)
    POST  /api/auth/login             Koneksyon (JSON)
    POST  /api/auth/token             Koneksyon fòm OAuth2 (pou bouton Authorize nan /docs)
    POST  /api/auth/refresh           Nouvo access token
    POST  /api/auth/logout            Antre nan jounal la
    GET   /api/auth/me                Kiyès mwen ye
    PATCH /api/auth/me                Chanje pwòp enfòmasyon
    POST  /api/auth/change-password   Chanje modpas
    GET   /api/auth/identity          Tout sa frontend lan bezwen apre koneksyon
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import CurrentUser, DbSession
from ..models import AuditLog, Employee, Organization, User, UserRole
from ..schemas import (
    LoginRequest,
    Message,
    PasswordChange,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserOut,
)
from ..security import (
    REFRESH_TOKEN,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger("konbit")

router = APIRouter()


# ---------------------------------------------------------------------------
# ZOUTI ENTÈN
# ---------------------------------------------------------------------------

def _log(
    db: Session,
    request: Request,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    changes: Optional[str] = None,
) -> None:
    """Ekri nan jounal odit la. Pa janm kite sa kase yon rekèt."""
    try:
        db.add(AuditLog(
            organization_id=user.organization_id if user else None,
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Nou pa t ka ekri nan jounal odit la.", exc_info=True)


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(
            user_id=user.id,
            role=user.role.value,
            organization_id=user.organization_id,
        ),
        refresh_token=create_refresh_token(user_id=user.id),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def _authenticate(db: Session, email: str, password: str) -> User:
    """
    Mesaj erè a rete menm bagay la pou move imel ak move modpas.
    Si ou di 'imel sa a pa egziste', ou ede yon atakè jwenn ki kont ki reyèl.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Imel oswa modpas la pa kòrèk.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None:
        # Fo verifikasyon: konsa tan reponn lan rete menm jan, epi yon atakè
        # pa ka mezire tan an pou l devine ki imel ki egziste.
        verify_password(password, "$2b$12$" + "x" * 53)
        raise invalid

    if user.failed_login_count >= settings.max_failed_logins:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Kont lan bloke apre twòp esè. Kontakte administratè w la.",
        )

    if not verify_password(password, user.hashed_password):
        user.failed_login_count += 1
        db.commit()
        raise invalid

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kont sa a dezaktive.",
        )

    user.failed_login_count = 0
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# ENSKRIPSYON YON BIZNIS
# ---------------------------------------------------------------------------

@router.post("/signup", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request, db: DbSession):
    """
    Kreye yon nouvo biznis ak premye administratè l la.
    Se sèl fason yon Organization kreye — pa gen endpoint separe pou sa.
    """
    slug = payload.organization.slug.lower().strip()
    if db.query(Organization).filter(Organization.slug == slug).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Idantifyan '{slug}' la deja pran. Chwazi yon lòt.",
        )

    email = payload.admin_email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Yon kont ak imel sa a deja egziste.",
        )

    problems = validate_password_strength(payload.admin_password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=problems,
        )

    org_data = payload.organization.model_dump()
    org_data["slug"] = slug

    try:
        org = Organization(**org_data)
        db.add(org)
        db.flush()          # pou nou jwenn org.id san nou pa komite

        admin = User(
            organization_id=org.id,
            email=email,
            hashed_password=hash_password(payload.admin_password),
            full_name=payload.admin_full_name.strip(),
            role=UserRole.ORG_ADMIN,
            is_active=True,
            email_verified=False,
        )
        db.add(admin)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Signup echwe")
        if not settings.is_production:
            # Nan devlopman nou montre vrè erè a pou nou ka korije l.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{type(exc).__name__}: {exc}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nou pa t ka kreye kont lan.",
        )

    db.refresh(admin)
    _log(db, request, admin, "create", "organization", org.id)
    return _issue_tokens(admin)


# ---------------------------------------------------------------------------
# KONEKSYON
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, request: Request, db: DbSession):
    user = _authenticate(db, payload.email, payload.password)
    _log(db, request, user, "login", "user", user.id)
    return _issue_tokens(user)


@router.post("/token", response_model=TokenPair, include_in_schema=False)
def login_oauth_form(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: DbSession,
):
    """Menm bagay ak /login, men ak fòm OAuth2. Se sa bouton 'Authorize' nan /docs sèvi."""
    user = _authenticate(db, form.username, form.password)
    _log(db, request, user, "login", "user", user.id)
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbSession):
    data = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token an pa valab oswa li ekspire.",
        )

    user = db.query(User).filter(User.id == int(data["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kont lan pa disponib.",
        )

    # Nou re-li wòl la nan baz done a: si HR chanje l, nouvo token an ap gen bon wòl la.
    return _issue_tokens(user)


@router.post("/logout", response_model=Message)
def logout(user: CurrentUser, request: Request, db: DbSession):
    """
    ATANSYON: JWT pa ka revoke san yon lis nwa. Kounye a sa a se sèlman
    yon antre nan jounal la — se frontend lan ki dwe efase token an.
    Si ou bezwen vrè revokasyon, ajoute yon tab `revoked_tokens` sou chan `jti`.
    """
    _log(db, request, user, "logout", "user", user.id)
    return Message(detail="Ou dekonekte.")


# ---------------------------------------------------------------------------
# PWÒP KONT MWEN
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser):
    return user


class MeUpdate(BaseModel):
    full_name: Optional[str] = None
    preferred_language: Optional[str] = None


@router.patch("/me", response_model=UserOut)
def update_me(payload: MeUpdate, user: CurrentUser, db: DbSession):
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", response_model=Message)
def change_password(
    payload: PasswordChange,
    user: CurrentUser,
    request: Request,
    db: DbSession,
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Modpas aktyèl la pa kòrèk.",
        )

    problems = validate_password_strength(payload.new_password)
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=problems,
        )

    if verify_password(payload.new_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nouvo modpas la dwe diferan de ansyen an.",
        )

    user.hashed_password = hash_password(payload.new_password)
    user.failed_login_count = 0
    db.commit()
    _log(db, request, user, "change_password", "user", user.id)
    return Message(detail="Modpas la chanje.")


# ---------------------------------------------------------------------------
# KIYÈS MWEN YE NAN BIZNIS LAN
# ---------------------------------------------------------------------------

class Identity(BaseModel):
    user: UserOut
    organization_name: Optional[str] = None
    employee_id: Optional[int] = None
    employee_number: Optional[str] = None
    department_id: Optional[int] = None
    manager_id: Optional[int] = None


@router.get("/identity", response_model=Identity)
def read_identity(user: CurrentUser, db: DbSession):
    """Tout sa frontend lan bezwen apre koneksyon pou l konstwi meni an."""
    org = None
    if user.organization_id:
        org = db.query(Organization).filter(
            Organization.id == user.organization_id
        ).first()

    emp = db.query(Employee).filter(Employee.user_id == user.id).first()

    return Identity(
        user=UserOut.model_validate(user),
        organization_name=org.name if org else None,
        employee_id=emp.id if emp else None,
        employee_number=emp.employee_number if emp else None,
        department_id=emp.department_id if emp else None,
        manager_id=emp.manager_id if emp else None,
    )