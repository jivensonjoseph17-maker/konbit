from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.security import get_current_user, verify_password, get_password_hash, create_access_token
from app.database import get_db
from app.models import User
from app.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserLogin(BaseModel):
    email: str
    password: str

@router.post("/token")
async def login_for_access_token(
    user_credentials: UserLogin, 
    db: Session = Depends(get_db)
):
    # Chèche itilizatè a nan baz done a pa imèl
    user = db.query(User).filter(User.email == user_credentials.email).first()
    
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Imèl oswa modpas la pa kòrèk",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Kreye token an
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: dict, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.get("email")).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Imèl sa a deja anrejistre")
    
    hashed_pwd = get_password_hash(user_data.get("password"))
    new_user = User(
        email=user_data.get("email"),
        hashed_password=hashed_pwd,
        full_name=user_data.get("full_name"),
        phone=user_data.get("phone"),
        role=user_data.get("role", "applicant"),
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Kont ou kreye ak siksè"}

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user