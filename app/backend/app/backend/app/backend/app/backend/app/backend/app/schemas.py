from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str
    role: str = "job_seeker"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    phone: str
    role: str
    created_at: datetime
    class Config:
        from_attributes = True

class ProfileCreate(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[str] = None
    experience_years: int = 0
    education: Optional[str] = None
    languages: Optional[str] = None
    expected_salary_min: Optional[float] = None
    expected_salary_max: Optional[float] = None
    preferred_job_type: Optional[str] = None
    preferred_location: Optional[str] = None

class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    rnc: Optional[str] = None

class JobCreate(BaseModel):
    title: str
    description: str
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    job_type: str = "full_time"
    location: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "HTG"

class ApplicationCreate(BaseModel):
    cover_letter: Optional[str] = None

class LeaveCreate(BaseModel):
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"