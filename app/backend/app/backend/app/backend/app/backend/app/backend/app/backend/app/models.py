from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String, default="job_seeker")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    profile = relationship("Profile", back_populates="user", uselist=False)
    company = relationship("Company", back_populates="owner", uselist=False)
    applications = relationship("Application", back_populates="applicant")
    attendances = relationship("Attendance", back_populates="employee")
    leaves = relationship("Leave", back_populates="employee")
    payrolls = relationship("Payroll", back_populates="employee")


class Profile(Base):
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    headline = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    skills = Column(String, nullable=True)
    experience_years = Column(Integer, default=0)
    education = Column(Text, nullable=True)
    languages = Column(String, nullable=True)
    resume_url = Column(String, nullable=True)
    expected_salary_min = Column(Float, nullable=True)
    expected_salary_max = Column(Float, nullable=True)
    preferred_job_type = Column(String, nullable=True)
    preferred_location = Column(String, nullable=True)
    is_open_to_work = Column(Boolean, default=True)
    
    user = relationship("User", back_populates="profile")


class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, index=True)
    description = Column(Text, nullable=True)
    industry = Column(String, nullable=True)
    website = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    location = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    rnc = Column(String, nullable=True)
    bank_name = Column(String, nullable=True)
    bank_account = Column(String, nullable=True)
    moncash_number = Column(String, nullable=True)
    natcash_number = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    owner = relationship("User", back_populates="company")
    jobs = relationship("Job", back_populates="company")
    employees = relationship("Employee", back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    posted_by = Column(Integer, ForeignKey("users.id"))
    title = Column(String, index=True)
    description = Column(Text)
    requirements = Column(Text, nullable=True)
    responsibilities = Column(Text, nullable=True)
    job_type = Column(String, default="full_time")
    location = Column(String, nullable=True)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    currency = Column(String, default="HTG")
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    company = relationship("Company", back_populates="jobs")
    applications = relationship("Application", back_populates="job")


class Application(Base):
    __tablename__ = "applications"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    applicant_id = Column(Integer, ForeignKey("users.id"))
    cover_letter = Column(Text, nullable=True)
    status = Column(String, default="pending")
    interview_date = Column(DateTime(timezone=True), nullable=True)
    interview_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="applications")
    applicant = relationship("User", back_populates="applications")
    offer = relationship("Offer", back_populates="application", uselist=False)

    

class Offer(Base):
    __tablename__ = "offers"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    sent_by = Column(Integer, ForeignKey("users.id"))
    position = Column(String)
    salary = Column(Float)
    salary_currency = Column(String, default="HTG")
    job_type = Column(String)
    start_date = Column(DateTime(timezone=True))
    health_insurance = Column(Boolean, default=False)
    vacation_days = Column(Integer, default=0)
    other_benefits = Column(Text, nullable=True)
    offer_letter_content = Column(Text)
    status = Column(String, default="draft")
    sent_at = Column(DateTime(timezone=True), nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    
    application = relationship("Application", back_populates="offer")


class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    position = Column(String)
    department = Column(String, nullable=True)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True), nullable=True)
    salary = Column(Float)
    salary_currency = Column(String, default="HTG")
    pay_frequency = Column(String, default="monthly")
    is_active = Column(Boolean, default=True)
    moncash_number = Column(String, nullable=True)
    natcash_number = Column(String, nullable=True)
    bank_name = Column(String, nullable=True)
    bank_account = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    company = relationship("Company", back_populates="employees")
    user = relationship("User")


class Attendance(Base):
    __tablename__ = "attendances"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    date = Column(DateTime(timezone=True))
    clock_in = Column(DateTime(timezone=True))
    clock_out = Column(DateTime(timezone=True), nullable=True)
    clock_in_lat = Column(Float, nullable=True)
    clock_in_lng = Column(Float, nullable=True)
    clock_out_lat = Column(Float, nullable=True)
    clock_out_lng = Column(Float, nullable=True)
    clock_in_photo_url = Column(String, nullable=True)
    clock_out_photo_url = Column(String, nullable=True)
    status = Column(String, default="present")
    notes = Column(Text, nullable=True)
    total_hours = Column(Float, nullable=True)
    
    employee = relationship("User", back_populates="attendances")


class Leave(Base):
    __tablename__ = "leaves"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    leave_type = Column(String)
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    days_requested = Column(Integer)
    reason = Column(Text, nullable=True)
    status = Column(String, default="pending")
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    responded_at = Column(DateTime(timezone=True), nullable=True)
    response_notes = Column(Text, nullable=True)
    
    employee = relationship("User", back_populates="leaves")


class Payroll(Base):
    __tablename__ = "payrolls"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    base_salary = Column(Float)
    overtime_hours = Column(Float, default=0)
    overtime_pay = Column(Float, default=0)
    bonuses = Column(Float, default=0)
    deductions = Column(Float, default=0)
    total_pay = Column(Float)
    payment_method = Column(String)
    payment_reference = Column(String, nullable=True)
    status = Column(String, default="pending")
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    employee = relationship("User", back_populates="payrolls")