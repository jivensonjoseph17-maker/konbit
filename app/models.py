from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(String, default="job_seeker")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    profile = relationship("Profile", back_populates="user", uselist=False)
    applications = relationship("Application", back_populates="user", foreign_keys="Application.user_id")
    offers = relationship("Offer", back_populates="user")
    attendances = relationship("Attendance", back_populates="user")
    leaves = relationship("Leave", back_populates="user")
    companies = relationship("Company", back_populates="owner")

class Profile(Base):
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    headline = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    skills = Column(Text, nullable=True)
    experience_years = Column(Integer, default=0)
    education = Column(Text, nullable=True)
    languages = Column(String, nullable=True)
    expected_salary_min = Column(Float, nullable=True)
    expected_salary_max = Column(Float, nullable=True)
    preferred_job_type = Column(String, nullable=True)
    preferred_location = Column(String, nullable=True)
    
    user = relationship("User", back_populates="profile")

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    industry = Column(String, nullable=True)
    website = Column(String, nullable=True)
    location = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    rnc = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="companies")
    jobs = relationship("Job", back_populates="company")
    employees = relationship("Employee", back_populates="company")

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    requirements = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    job_type = Column(String, default="full_time")
    location = Column(String, nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    currency = Column(String, default="HTG")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    company_id = Column(Integer, ForeignKey("companies.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    
    company = relationship("Company", back_populates="jobs")
    applications = relationship("Application", back_populates="job")
    poster = relationship("User")

class Application(Base):
    __tablename__ = "applications"
    
    id = Column(Integer, primary_key=True, index=True)
    cover_letter = Column(Text, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    applicant_id = Column(Integer, ForeignKey("users.id"))
    
    job = relationship("Job", back_populates="applications")
    user = relationship("User", back_populates="applications", foreign_keys=[user_id])
    offers = relationship("Offer", back_populates="application")
    applicant = relationship("User", foreign_keys=[applicant_id])

class Offer(Base):
    __tablename__ = "offers"
    
    id = Column(Integer, primary_key=True, index=True)
    salary = Column(Float, nullable=False)
    start_date = Column(DateTime, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    application_id = Column(Integer, ForeignKey("applications.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    application = relationship("Application", back_populates="offers")
    user = relationship("User", back_populates="offers")

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    position = Column(String, nullable=True)
    department = Column(String, nullable=True)
    hire_date = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    company = relationship("Company", back_populates="employees")
    attendances = relationship("Attendance", back_populates="employee")
    leaves = relationship("Leave", back_populates="employee")

class Attendance(Base):
    __tablename__ = "attendances"
    
    id = Column(Integer, primary_key=True, index=True)
    check_in = Column(DateTime, nullable=False)
    check_out = Column(DateTime, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="present")
    user_id = Column(Integer, ForeignKey("users.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    
    user = relationship("User", back_populates="attendances")
    employee = relationship("Employee", back_populates="attendances")

class Leave(Base):
    __tablename__ = "leaves"
    
    id = Column(Integer, primary_key=True, index=True)
    leave_type = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"))
    employee_id = Column(Integer, ForeignKey("employees.id"))
    
    user = relationship("User", back_populates="leaves")
    employee = relationship("Employee", back_populates="leaves")