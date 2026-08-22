from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Profile
from app.schemas import UserCreate, UserLogin, UserResponse, ProfileCreate, ProfileResponse, Token
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email deja itilize")
    if db.query(User).filter(User.phone == user.phone).first():
        raise HTTPException(status_code=400, detail="Nimewo telefòn deja itilize")
    
    hashed = get_password_hash(user.password)
    new_user = User(
        email=user.email,
        phone=user.phone,
        hashed_password=hashed,
        full_name=user.full_name,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    profile = Profile(user_id=new_user.id)
    db.add(profile)
    db.commit()
    
    return new_user

@router.post("/login", response_model=Token)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email oswa modpas pa kòrèk")
    token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    return {"access_token": token}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return current_user

@router.put("/profile", response_model=ProfileResponse)
def update_profile(profile: ProfileCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db_profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Pwofil pa jwenn")
    
    for key, value in profile.dict().items():
        setattr(db_profile, key, value)
    
    db.commit()
    db.refresh(db_profile)
    return db_profile