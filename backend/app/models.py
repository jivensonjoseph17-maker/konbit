"""
Konbit — Modèl baz done (SQLAlchemy)

Prensip ki gide fichye sa a:
  1. MULTI-TENANT: chak done ki pou yon biznis gen yon `organization_id`.
     Chak rekèt nan routers yo DWE filtre sou li. San sa, biznis A ap wè
     done biznis B.
  2. SOFT DELETE: nou pa efase done HR (dosye anplwaye se dokiman legal).
     Nou make yo `is_active = False`.
  3. LAJAN AN SANTIM: tout montan se Integer an santim (oswa "kòb"), pa Float.
     Float ap ba ou erè awondisman sou fich peye. 1000.50 HTG => 100050.
"""

import enum
from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


# ---------------------------------------------------------------------------
# ENIMERASYON
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"      # Ekip Konbit la
    ORG_ADMIN = "org_admin"          # Patwon / mèt biznis la
    HR = "hr"                        # Jesyonè resous imèn
    MANAGER = "manager"              # Sipèvizè ekip
    EMPLOYEE = "employee"            # Anplwaye regilye
    APPLICANT = "applicant"          # Moun k ap aplike (pa anplwaye ankò)


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERN = "intern"
    SEASONAL = "seasonal"


class JobStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ApplicationStage(str, enum.Enum):
    RECEIVED = "received"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class OfferStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class AttendanceStatus(str, enum.Enum):
    OPEN = "open"            # Clock in fèt, clock out poko
    CLOSED = "closed"
    MISSING_OUT = "missing_out"   # Bliye clock out
    ADJUSTED = "adjusted"    # HR korije l alamen


class LeaveType(str, enum.Enum):
    VACATION = "vacation"
    SICK = "sick"
    MATERNITY = "maternity"
    PATERNITY = "paternity"
    BEREAVEMENT = "bereavement"
    UNPAID = "unpaid"
    OTHER = "other"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PayrollStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentMethod(str, enum.Enum):
    """Se sa ki reponn 'si se chèk oubyen depo'."""
    CHECK = "check"
    DIRECT_DEPOSIT = "direct_deposit"
    CASH = "cash"
    MONCASH = "moncash"
    NATCASH = "natcash"


class Currency(str, enum.Enum):
    HTG = "HTG"
    USD = "USD"


class FeedbackType(str, enum.Enum):
    PRAISE = "praise"
    CONCERN = "concern"
    SUGGESTION = "suggestion"
    PEER_REVIEW = "peer_review"


# ---------------------------------------------------------------------------
# MIXIN
# ---------------------------------------------------------------------------

class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OrgMixin:
    """Tout tab ki gen done yon biznis dwe eritye sa a."""
    @property
    def tenant_key(self):
        return self.organization_id


# ---------------------------------------------------------------------------
# 1. ÒGANIZASYON AK ITILIZATÈ
# ---------------------------------------------------------------------------

class Organization(Base, TimestampMixin):
    """Yon biznis ki enskri sou Konbit. Se rasin multi-tenant lan."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)  # pou URL
    legal_name = Column(String(200))
    tax_id = Column(String(50))          # NIF / Patant
    industry = Column(String(100))
    address = Column(Text)
    city = Column(String(100))
    country = Column(String(2), default="HT")
    phone = Column(String(50))
    email = Column(String(255))
    logo_url = Column(String(500))
    default_currency = Column(SQLEnum(Currency), default=Currency.HTG, nullable=False)
    timezone = Column(String(50), default="America/Port-au-Prince")
    is_active = Column(Boolean, default=True, nullable=False)

    users = relationship("User", back_populates="organization")
    employees = relationship("Employee", back_populates="organization")
    departments = relationship("Department", back_populates="organization")


class User(Base, TimestampMixin):
    """Kont koneksyon. Separe ak Employee: yon aplikan gen yon User san Employee."""
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_user_org_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    # nullable=True paske SUPER_ADMIN ak APPLICANT ka pa gen òganizasyon

    email = Column(String(255), index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.EMPLOYEE, nullable=False)
    preferred_language = Column(String(5), default="ht")   # ht, fr, en, es
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    failed_login_count = Column(Integer, default=0, nullable=False)

    organization = relationship("Organization", back_populates="users")
    employee = relationship("Employee", back_populates="user", uselist=False)


# ---------------------------------------------------------------------------
# 2. STRIKTI ÒGANIZASYONÈL
# ---------------------------------------------------------------------------

class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String(150), nullable=False)
    code = Column(String(30))
    description = Column(Text)
    parent_id = Column(Integer, ForeignKey("departments.id"))    # depatman anndan depatman
    # use_alter: kreye tab la san kontrent sa a, epi ajoute l apre ak ALTER TABLE.
    # San sa gen yon bouk: departments -> employees -> departments, epi
    # PostgreSQL pa ka kreye tab yo (SQLite pase, men li pa verifye).
    head_employee_id = Column(
        Integer,
        ForeignKey("employees.id", use_alter=True, name="fk_department_head_employee"),
    )
    is_active = Column(Boolean, default=True, nullable=False)

    organization = relationship("Organization", back_populates="departments")
    parent = relationship("Department", remote_side=[id], backref="sub_departments")


class Position(Base, TimestampMixin):
    """Tit travay la (ex: 'Kesye', 'Enjenyè AI'). Separe ak moun ki okipe l la."""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    title = Column(String(150), nullable=False)
    level = Column(String(50))                  # junior, senior, lead...
    description = Column(Text)
    min_salary = Column(Integer)                # an santim
    max_salary = Column(Integer)
    currency = Column(SQLEnum(Currency), default=Currency.HTG)
    is_active = Column(Boolean, default=True, nullable=False)


class Employee(Base, TimestampMixin):
    """Dosye anplwaye a. `manager_id` se sa ki bati òganigram lan."""
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_number", name="uq_emp_org_number"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)

    employee_number = Column(String(50), nullable=False)   # ex: KB-0001
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    personal_email = Column(String(255))
    phone = Column(String(50))
    date_of_birth = Column(Date)
    national_id = Column(String(60))            # NIF / CIN
    address = Column(Text)
    city = Column(String(100))
    emergency_contact_name = Column(String(200))
    emergency_contact_phone = Column(String(50))
    photo_url = Column(String(500))

    # Travay
    department_id = Column(Integer, ForeignKey("departments.id"), index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), index=True)
    manager_id = Column(Integer, ForeignKey("employees.id"), index=True)   # <-- ÒGANIGRAM
    employment_type = Column(SQLEnum(EmploymentType), default=EmploymentType.FULL_TIME)
    status = Column(SQLEnum(EmploymentStatus), default=EmploymentStatus.ACTIVE, nullable=False)
    hire_date = Column(Date, nullable=False)
    termination_date = Column(Date)
    termination_reason = Column(Text)

    # Salè de baz
    base_salary = Column(Integer)               # an santim, pa peryòd
    hourly_rate = Column(Integer)               # an santim, pou moun pa lè
    currency = Column(SQLEnum(Currency), default=Currency.HTG)

    # Peyman
    preferred_payment_method = Column(SQLEnum(PaymentMethod), default=PaymentMethod.CHECK)
    bank_name = Column(String(150))
    bank_account_number = Column(String(80))    # chiffre sa nan pwodiksyon
    mobile_money_number = Column(String(50))    # MonCash / NatCash

    is_active = Column(Boolean, default=True, nullable=False)

    organization = relationship("Organization", back_populates="employees")
    user = relationship("User", back_populates="employee")
    manager = relationship("Employee", remote_side=[id], backref="direct_reports")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def chain_of_command(self, max_depth: int = 10) -> list:
        """Tout moun ki sou tèt anplwaye a, soti nan manadjè dirèk la jouk anwo."""
        chain, current, depth = [], self.manager, 0
        while current is not None and depth < max_depth:
            chain.append(current)
            current = current.manager
            depth += 1
        return chain


# ---------------------------------------------------------------------------
# 3. REKRITMAN
# ---------------------------------------------------------------------------

class JobPosting(Base, TimestampMixin):
    __tablename__ = "job_postings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    position_id = Column(Integer, ForeignKey("positions.id"))
    created_by_id = Column(Integer, ForeignKey("users.id"))

    title = Column(String(200), index=True, nullable=False)
    slug = Column(String(220), index=True)
    description = Column(Text)
    requirements = Column(Text)
    responsibilities = Column(Text)
    location = Column(String(150))
    is_remote = Column(Boolean, default=False)
    employment_type = Column(SQLEnum(EmploymentType), default=EmploymentType.FULL_TIME)
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    currency = Column(SQLEnum(Currency), default=Currency.HTG)
    show_salary = Column(Boolean, default=False)
    openings = Column(Integer, default=1)
    status = Column(SQLEnum(JobStatus), default=JobStatus.DRAFT, nullable=False)
    published_at = Column(DateTime(timezone=True))
    closes_at = Column(DateTime(timezone=True))
    view_count = Column(Integer, default=0)

    applications = relationship("Application", back_populates="job_posting")


class Application(Base, TimestampMixin):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    job_posting_id = Column(Integer, ForeignKey("job_postings.id"), index=True, nullable=False)
    applicant_user_id = Column(Integer, ForeignKey("users.id"), index=True)

    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    resume_url = Column(String(500))
    cover_letter = Column(Text)
    stage = Column(SQLEnum(ApplicationStage), default=ApplicationStage.RECEIVED, nullable=False)
    rating = Column(Integer)                 # 1-5, evalyasyon entèn
    internal_notes = Column(Text)
    rejected_reason = Column(Text)
    source = Column(String(100))             # site a, referans, rezo sosyal...

    job_posting = relationship("JobPosting", back_populates="applications")
    interviews = relationship("Interview", back_populates="application")


class Interview(Base, TimestampMixin):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), index=True, nullable=False)
    interviewer_id = Column(Integer, ForeignKey("employees.id"))

    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=45)
    location = Column(String(255))           # adrès oswa lyen videyo
    round_number = Column(Integer, default=1)
    notes = Column(Text)
    score = Column(Integer)                  # 1-5
    completed = Column(Boolean, default=False)

    application = relationship("Application", back_populates="interviews")


class Offer(Base, TimestampMixin):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), index=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    salary = Column(Integer, nullable=False)          # an santim
    currency = Column(SQLEnum(Currency), default=Currency.HTG)
    employment_type = Column(SQLEnum(EmploymentType), default=EmploymentType.FULL_TIME)
    start_date = Column(Date)
    expires_at = Column(DateTime(timezone=True))
    status = Column(SQLEnum(OfferStatus), default=OfferStatus.DRAFT, nullable=False)
    document_url = Column(String(500))
    responded_at = Column(DateTime(timezone=True))
    notes = Column(Text)


# ---------------------------------------------------------------------------
# 4. TAN, PREZANS AK KONJE
# ---------------------------------------------------------------------------

class TimeEntry(Base, TimestampMixin):
    """Clock in / clock out."""
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)

    work_date = Column(Date, index=True, nullable=False)
    clock_in_at = Column(DateTime(timezone=True), nullable=False)
    clock_out_at = Column(DateTime(timezone=True))
    break_minutes = Column(Integer, default=0)
    worked_minutes = Column(Integer)             # kalkile lè clock out fèt
    overtime_minutes = Column(Integer, default=0)
    status = Column(SQLEnum(AttendanceStatus), default=AttendanceStatus.OPEN, nullable=False)

    # Prèv kote moun nan te ye (anti-fwod)
    clock_in_lat = Column(Numeric(10, 7))
    clock_in_lng = Column(Numeric(10, 7))
    clock_out_lat = Column(Numeric(10, 7))
    clock_out_lng = Column(Numeric(10, 7))
    clock_in_ip = Column(String(45))
    device_info = Column(String(255))

    # Koreksyon HR
    adjusted_by_id = Column(Integer, ForeignKey("users.id"))
    adjustment_reason = Column(Text)

    employee = relationship("Employee", backref="time_entries")


class LeaveBalance(Base, TimestampMixin):
    """Konbyen jou konje yon anplwaye genyen pou yon ane."""
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type", "year", name="uq_balance_emp_type_year"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    leave_type = Column(SQLEnum(LeaveType), nullable=False)
    year = Column(Integer, nullable=False)
    entitled_days = Column(Numeric(5, 2), default=0)
    used_days = Column(Numeric(5, 2), default=0)
    carried_over_days = Column(Numeric(5, 2), default=0)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)

    leave_type = Column(SQLEnum(LeaveType), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_days = Column(Numeric(5, 2), nullable=False)
    reason = Column(Text)
    attachment_url = Column(String(500))         # sètifika doktè, elatriye
    status = Column(SQLEnum(RequestStatus), default=RequestStatus.PENDING, nullable=False)

    approver_id = Column(Integer, ForeignKey("employees.id"))
    approved_at = Column(DateTime(timezone=True))
    decision_note = Column(Text)

    employee = relationship("Employee", foreign_keys=[employee_id], backref="leave_requests")


# ---------------------------------------------------------------------------
# 5. PEYÒL
# ---------------------------------------------------------------------------

class PayPeriod(Base, TimestampMixin):
    __tablename__ = "pay_periods"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)       # "Septanm 2026 - 2yèm kenzèn"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    pay_date = Column(Date, nullable=False)
    status = Column(SQLEnum(PayrollStatus), default=PayrollStatus.DRAFT, nullable=False)
    approved_by_id = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True))

    payslips = relationship("Payslip", back_populates="pay_period")


class Payslip(Base, TimestampMixin):
    """Fich peye. Se la anplwaye a wè si se chèk oswa depo."""
    __tablename__ = "payslips"
    __table_args__ = (
        UniqueConstraint("pay_period_id", "employee_id", name="uq_payslip_period_emp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)

    # Tout montan an santim
    base_amount = Column(Integer, default=0, nullable=False)
    overtime_amount = Column(Integer, default=0)
    bonus_amount = Column(Integer, default=0)
    gross_amount = Column(Integer, default=0, nullable=False)

    # --- Dediksyon (Ayiti) ---
    # IRI sou salè debaz la, dapre baremn pwogresif 5 tranch la,
    # aplike sou 90% brit la (abatman espesyal 10%, atik 92).
    tax_amount = Column(Integer, default=0)

    # Retni alasous fiks sou bonis, etrèn, prim ak èdtan siplemantè.
    # Se yon prelèvman SEPARE de baremn nan (atik 96, dekrè 29 sept. 1986).
    # 10% jouk 30 sept. 2026; 15% apati 1ye okt. 2026 (bidjè rektifikatif
    # 2025-2026, Moniteur 5 jen 2026; antre an vigè ranvwaye pa MEF 14 jiyè 2026).
    supplemental_tax_amount = Column(Integer, default=0)

    ona_amount = Column(Integer, default=0)          # ONA — retrèt, 6%
    ofatma_amount = Column(Integer, default=0)       # OFATMA — sante, 3%

    # Kontribisyon Fon Jesyon ak Devlopman Kolektivite Teritoryal yo,
    # 1% sou tout salè brit ki egal oswa depase 5 000 HTG pa mwa.
    cfgdct_amount = Column(Integer, default=0)

    # Fon dijans (FDU) ak Kès Asistans Sosyal (CAS), 1% sou salè brit.
    fdu_cas_amount = Column(Integer, default=0)

    other_deductions = Column(Integer, default=0)
    net_amount = Column(Integer, default=0, nullable=False)
    currency = Column(SQLEnum(Currency), default=Currency.HTG, nullable=False)

    hours_worked = Column(Numeric(7, 2))
    overtime_hours = Column(Numeric(7, 2))

    # Peyman
    payment_method = Column(SQLEnum(PaymentMethod), nullable=False)
    check_number = Column(String(50))                # si se chèk
    bank_name = Column(String(150))                  # si se depo
    account_last4 = Column(String(4))                # pa estoke tout nimewo a
    transaction_ref = Column(String(120))            # MonCash / NatCash ref
    paid_at = Column(DateTime(timezone=True))

    status = Column(SQLEnum(PayrollStatus), default=PayrollStatus.DRAFT, nullable=False)
    pdf_url = Column(String(500))
    notes = Column(Text)

    pay_period = relationship("PayPeriod", back_populates="payslips")
    employee = relationship("Employee", backref="payslips")


# ---------------------------------------------------------------------------
# 6. FÒMASYON (VIDEYO)
# ---------------------------------------------------------------------------

class Course(Base, TimestampMixin):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=True)
    # nullable => kou Konbit bay tout biznis yo

    title = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    thumbnail_url = Column(String(500))
    language = Column(String(5), default="ht")
    is_mandatory = Column(Boolean, default=False)
    target_department_id = Column(Integer, ForeignKey("departments.id"))
    passing_score = Column(Integer, default=70)
    is_published = Column(Boolean, default=False, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))

    lessons = relationship("Lesson", back_populates="course", order_by="Lesson.order_index")


class Lesson(Base, TimestampMixin):
    """Yon videyo (oswa dokiman) anndan yon kou."""
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    video_url = Column(String(500))
    attachment_url = Column(String(500))
    duration_seconds = Column(Integer)
    order_index = Column(Integer, default=0, nullable=False)
    is_required = Column(Boolean, default=True)

    course = relationship("Course", back_populates="lessons")


class Enrollment(Base, TimestampMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("course_id", "employee_id", name="uq_enroll_course_emp"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)

    assigned_by_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    progress_percent = Column(Integer, default=0, nullable=False)
    completed_at = Column(DateTime(timezone=True))
    score = Column(Integer)
    certificate_url = Column(String(500))

    employee = relationship("Employee", backref="enrollments")


class LessonProgress(Base, TimestampMixin):
    """Ki kote anplwaye a rive nan yon videyo — pou l ka kontinye pita."""
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("enrollment_id", "lesson_id", name="uq_progress_enroll_lesson"),
    )

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("enrollments.id"), index=True, nullable=False)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), index=True, nullable=False)
    seconds_watched = Column(Integer, default=0)
    last_position_seconds = Column(Integer, default=0)
    completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 7. FIDBAK AK PÈFÒMANS
# ---------------------------------------------------------------------------

class Feedback(Base, TimestampMixin):
    """Fidbak lib. Ka anonim — se poutèt sa author_id nullable."""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    author_id = Column(Integer, ForeignKey("employees.id"), index=True)
    subject_employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    # subject nullable => fidbak sou konpayi a an jeneral

    feedback_type = Column(SQLEnum(FeedbackType), default=FeedbackType.SUGGESTION, nullable=False)
    title = Column(String(200))
    body = Column(Text, nullable=False)
    is_anonymous = Column(Boolean, default=False, nullable=False)
    is_private = Column(Boolean, default=True, nullable=False)   # HR + manadjè sèlman
    acknowledged_at = Column(DateTime(timezone=True))
    response = Column(Text)


class PerformanceReview(Base, TimestampMixin):
    __tablename__ = "performance_reviews"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("employees.id"), index=True)

    period_label = Column(String(100))        # "2026 - 1ye semès"
    period_start = Column(Date)
    period_end = Column(Date)
    overall_score = Column(Integer)           # 1-5
    strengths = Column(Text)
    improvements = Column(Text)
    goals = Column(Text)
    employee_comment = Column(Text)
    status = Column(SQLEnum(RequestStatus), default=RequestStatus.PENDING, nullable=False)
    finalized_at = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 8. DOKIMAN AK ODIT
# ---------------------------------------------------------------------------

class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))

    name = Column(String(255), nullable=False)
    category = Column(String(100))            # kontra, diplòm, ID, evalyasyon...
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    expires_at = Column(Date)                 # pou pèmi, viza, sètifika
    is_confidential = Column(Boolean, default=True, nullable=False)


class AuditLog(Base):
    """Kilès ki fè kisa. Obligatwa pou yon sistèm HR."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    action = Column(String(100), nullable=False)       # create, update, delete, view
    entity_type = Column(String(100), nullable=False)  # "payslip", "employee"...
    entity_id = Column(Integer)
    changes = Column(Text)                             # JSON anvan/apre
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text)
    link_url = Column(String(500))
    category = Column(String(50))            # leave, payroll, training, hiring
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# 9. KONTNI PAJ PIBLIK (sa ou te genyen deja)
# ---------------------------------------------------------------------------

class Professional(Base, TimestampMixin):
    """Moun ki parèt sou landing page Konbit la."""
    __tablename__ = "professionals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    role = Column(String(150))
    description = Column(Text)
    avatar = Column(String(500))
    order_index = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True, nullable=False)