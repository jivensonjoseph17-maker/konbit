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

class ProfileResponse(BaseModel):
    id: int
    user_id: int
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
    class Config:
        from_attributes = True

class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    rnc: Optional[str] = None

class CompanyResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    rnc: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True

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

class JobResponse(BaseModel):
    id: int
    title: str
    description: str
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    job_type: str
    location: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str
    is_active: bool
    created_at: datetime
    company_id: int
    class Config:
        from_attributes = True

class ApplicationCreate(BaseModel):
    cover_letter: Optional[str] = None

class ApplicationResponse(BaseModel):
    id: int
    cover_letter: Optional[str] = None
    status: str
    created_at: datetime
    job_id: int
    user_id: int
    class Config:
        from_attributes = True

class OfferCreate(BaseModel):
    application_id: int
    salary: float
    start_date: datetime

class OfferResponse(BaseModel):
    id: int
    salary: float
    start_date: datetime
    status: str
    created_at: datetime
    application_id: int
    user_id: int
    class Config:
        from_attributes = True

class LeaveCreate(BaseModel):
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None

class LeaveResponse(BaseModel):
    id: int
    leave_type: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None
    status: str
    created_at: datetime
    user_id: int
    employee_id: Optional[int] = None
    class Config:
        from_attributes = True

class EmployeeResponse(BaseModel):
    id: int
    user_id: int
    company_id: int
    position: Optional[str] = None
    department: Optional[str] = None
    hire_date: datetime
    is_active: bool
    class Config:
        from_attributes = True

class AttendanceResponse(BaseModel):
    id: int
    check_in: datetime
    check_out: Optional[datetime] = None
    date: datetime
    status: str
    user_id: int
    employee_id: Optional[int] = None
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"