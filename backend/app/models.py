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
    Time,
    UniqueConstraint,
    false,
    func,
    true,
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
    # Kijan anplwaye yo pwente: "phone" (telefòn yo), "kiosk" (tablèt biznis la
    # sèlman) oswa "both". Gade app/clock_mode.py.
    clock_mode = Column(String(10), default="phone", nullable=False, server_default="phone")
    # Chak konbyen tan biznis la peye: "weekly", "biweekly", "semimonthly", "monthly".
    pay_frequency = Column(String(12), default="monthly", nullable=False, server_default="monthly")
    # Zòn otorize pou pwentaj sou telefòn (routers/geofence.py):
    # "off" (pa verifye), "flag" (make l pou HR), "block" (refize klòk in).
    geofence_mode = Column(String(10), default="off", nullable=False, server_default="off")
    geofence_lat = Column(Numeric(10, 7))
    geofence_lng = Column(Numeric(10, 7))
    geofence_radius_m = Column(Integer)
    # Tablèt pwentaj: "number_pin" (nimewo + kòd) oswa "pin_only" (kòd sèlman).
    kiosk_pin_mode = Column(String(12), default="number_pin", nullable=False, server_default="number_pin")
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
    preferred_language = Column(String(5), default="ht")   # ht, fr, en, es…
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    failed_login_count = Column(Integer, default=0, nullable=False)
    # True apre HR kreye kont lan oswa jenere yon modpas tanporè: moun nan
    # dwe chwazi pwòp modpas li anvan li fè anyen (gade deps.get_current_user).
    must_change_password = Column(Boolean, default=False, nullable=False, server_default=false())
    # Chak token pote vèsyon sa a (claim "ver"). Dekonekte, chanje modpas oswa
    # yon reset HR ogmante l: tout ansyen token yo sispann mache (deps.py).
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    # Verifikasyon an 2 etap (TOTP, routers/mfa.py). Sekrè a ap chifre nan pati D.
    totp_secret = Column(String(64))
    totp_enabled = Column(Boolean, default=False, nullable=False, server_default=false())
    totp_last_step = Column(Integer)        # dènye fenèt 30 s ki sèvi: yon kòd pa sèvi 2 fwa

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
    # Direksyon (Pwopriyetè, Fondatè, Direktè...): parèt anlè òganigram lan.
    # Sa pa bay okenn dwa nan sistèm lan — dwa yo soti nan wòl kont lan.
    is_leadership = Column(Boolean, default=False, nullable=False, server_default=false())
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

    # False = moun nan nan òganigram lan, men pewòl la pa kalkile fich pou li
    # (pwopriyetè, fondatè ki pa touche salè oswa ki touche dividann).
    on_payroll = Column(Boolean, default=True, nullable=False, server_default=true())

    # Kòd pèsonèl pou pwente sou tablèt biznis la. Ache (PBKDF2), jamè an klè.
    # Gade routers/kiosk.py: 5 move kòd → bloke 15 minit.
    kiosk_pin_hash = Column(String(255))
    kiosk_pin_set_at = Column(DateTime(timezone=True))
    kiosk_failed_count = Column(Integer, default=0, nullable=False, server_default="0")
    kiosk_locked_until = Column(DateTime(timezone=True))
    # Mòd "kòd sèlman": HMAC(kle sekrè, "org:kòd") pou jwenn moun nan vit (routers/kiosk.py).
    kiosk_pin_lookup = Column(String(64), index=True)

    is_active = Column(Boolean, default=True, nullable=False)

    organization = relationship("Organization", back_populates="employees")
    user = relationship("User", back_populates="employee")
    manager = relationship("Employee", remote_side=[id], backref="direct_reports")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def has_bank_account(self) -> bool:
        """Pou frontend lan: gen yon nimewo kont — san nou pa janm voye nimewo a."""
        return bool((self.bank_account_number or "").strip())

    @property
    def has_kiosk_pin(self) -> bool:
        """Pou frontend lan: gen yon kòd kiyòsk — san nou pa janm voye l."""
        return bool(self.kiosk_pin_hash)

    @property
    def login_role(self):
        """Wòl kont koneksyon an (employee, manager, hr, org_admin), oswa None."""
        return self.user.role if self.user is not None else None

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
    device_info = Column(String(255))           # "kiosk:<id> <non>" si se tablèt la

    # Zòn otorize (routers/geofence.py): distans ak pozisyon biznis la, an mèt.
    # outside_zone: twò lwen, oswa moun nan pa t pataje pozisyon l (pou HR).
    clock_in_distance_m = Column(Integer)
    clock_out_distance_m = Column(Integer)
    outside_zone = Column(Boolean, default=False, nullable=False, server_default=false())

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
# 5. PEWÒL
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
    # Ranbousman avans sou salè (routers/salary_advances.py), apre enpo.
    advance_amount = Column(Integer, default=0, nullable=False, server_default="0")
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


from sqlalchemy import LargeBinary  # noqa: E402 — pou logo biznis la


class OrganizationLogo(Base):
    """
    Logo biznis la kòm fichye (routers/org_logo.py). Yon liy pa biznis.
    `data` se yon PNG NOU MENM te kreye apre netwayaj (maks 512 px).
    """
    __tablename__ = "organization_logos"

    organization_id = Column(Integer, ForeignKey("organizations.id"), primary_key=True)
    data = Column(LargeBinary, nullable=False)
    content_type = Column(String(30), nullable=False)
    sha256 = Column(String(64), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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


# ---------------------------------------------------------------------------
# REKRITMAN — KESYON FÒM APLIKASYON
#
# Chak biznis gen pwòp kesyon li. Kesyon "pa defo" yo (system_key pa vid)
# kreye otomatikman; HR ka modifye oswa dezaktive yo, men pa efase yo.
# Repons yo sere yon KOPI tèks kesyon an: si HR chanje kesyon an pita,
# ansyen aplikasyon yo toujou montre sa kandida a te vrèman wè.
# ---------------------------------------------------------------------------

from sqlalchemy import JSON  # noqa: E402


class QuestionType(str, enum.Enum):
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    YES_NO = "yes_no"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    NUMBER = "number"
    DATE = "date"
    URL = "url"


class ApplicationQuestion(Base, TimestampMixin):
    __tablename__ = "application_questions"
    __table_args__ = (
        UniqueConstraint("organization_id", "system_key", name="uq_question_org_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    # Vid = kesyon an parèt pou TOUT òf biznis la. Sinon, sèlman pou òf sa a.
    job_posting_id = Column(Integer, ForeignKey("job_postings.id"), index=True)

    system_key = Column(String(50))              # "city", "worked_here_before"... (kesyon pa defo)
    section = Column(String(30), nullable=False, default="other")
    label = Column(String(300), nullable=False)
    help_text = Column(String(500))
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    options = Column(JSON)                        # lis chwa pou single/multi_choice
    is_required = Column(Boolean, default=False, nullable=False)
    is_sensitive = Column(Boolean, default=False, nullable=False)   # HR/admin sèlman
    is_active = Column(Boolean, default=True, nullable=False)
    order_index = Column(Integer, default=0, nullable=False)

    # Kesyon an parèt sèlman si yon lòt kesyon gen yon sèten repons.
    # Egz: "Poukisa w te kite?" parèt sèlman si "Te deja travay isit?" = wi.
    condition_question_id = Column(Integer, ForeignKey("application_questions.id"))
    condition_value = Column(String(100))

    condition_question = relationship("ApplicationQuestion", remote_side=[id])


class ApplicationAnswer(Base, TimestampMixin):
    __tablename__ = "application_answers"
    __table_args__ = (
        UniqueConstraint("application_id", "question_id", name="uq_answer_app_question"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), index=True, nullable=False)
    question_id = Column(Integer, ForeignKey("application_questions.id"), index=True, nullable=False)

    # Kopi kesyon an nan moman kandida a te reponn
    question_label = Column(String(300), nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    section = Column(String(30), nullable=False)
    is_sensitive = Column(Boolean, default=False, nullable=False)

    value = Column(JSON)                          # tèks, bool, chif, lis...


# ---------------------------------------------------------------------------
# APWOBASYON TAN TRAVAY
#
# Manadjè a apwouve èdtan chak moun nan ekip li pou yon peryòd pewòl.
# San apwobasyon: pewòl la peye salè de baz la, men PA èdtan siplemantè.
# Yon apwobasyon BLOKE pwentaj peryòd la: HR dwe retire l anvan li korije.
# ---------------------------------------------------------------------------

class TimesheetStatus(str, enum.Enum):
    APPROVED = "approved"
    RETURNED = "returned"      # manadjè a voye l bay HR pou koreksyon


class TimesheetApproval(Base, TimestampMixin):
    __tablename__ = "timesheet_approvals"
    __table_args__ = (
        UniqueConstraint("employee_id", "pay_period_id", name="uq_timesheet_emp_period"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), index=True, nullable=False)

    status = Column(SQLEnum(TimesheetStatus), nullable=False)
    decided_by_id = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime(timezone=True))
    note = Column(Text)

    # Sa manadjè a te wè lè l te apwouve (pou odit)
    worked_minutes = Column(Integer, default=0)
    overtime_minutes = Column(Integer, default=0)


# ---------------------------------------------------------------------------
# ORÈ TRAVAY PA SEMÈN
#
# ShiftTemplate: modèl HR kreye yon sèl fwa ("Maten 7è–15è", "Lannwit 23è–7è").
# Shift: orè yon moun pou YON jou. Lè yo LOKAL biznis la (pa UTC): se lè
# moun nan ap gade sou revèy li. Si end_time <= start_time, orè a fini
# nan demen (ekip lannwit).
# Anplwaye a wè yon orè sèlman lè manadjè a pibliye l (is_published).
# ---------------------------------------------------------------------------

class ShiftTemplate(Base, TimestampMixin):
    __tablename__ = "shift_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String(80), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_minutes = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_shift_emp_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    template_id = Column(Integer, ForeignKey("shift_templates.id"))

    work_date = Column(Date, index=True, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_minutes = Column(Integer, default=0, nullable=False)
    note = Column(String(300))
    is_published = Column(Boolean, default=False, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))


# ---------------------------------------------------------------------------
# KIYÒSK — TABLÈT BIZNIS LA
#
# Admin aktive yon tablèt yon sèl fwa. Tablèt la resevwa yon token ki pa
# ka fè anyen lòt pase pwentaj (routers/kiosk.py). Nou estoke sha256 token
# an sèlman: si baz done a koule, token yo pa ka itilize.
# ---------------------------------------------------------------------------

class KioskDevice(Base, TimestampMixin):
    __tablename__ = "kiosk_devices"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)             # "Tablèt kès la"
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    last_seen_at = Column(DateTime(timezone=True))

    # Pwoteksyon kont moun k ap devine kòd
    failed_count = Column(Integer, default=0, nullable=False, server_default="0")
    locked_until = Column(DateTime(timezone=True))

    is_active = Column(Boolean, default=True, nullable=False, server_default=true())
    revoked_at = Column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# DEMANN CHANJMAN PEMAN (routers/payment_changes.py)
#
# Yon anplwaye pa chanje kont labank / MonCash li dirèkteman: li voye yon
# demann (ak modpas li), epi yon LÒT moun HR apwouve l. Metòd ak estati yo se
# String (pa Enum PostgreSQL) pou migrasyon an rete senp.
# ---------------------------------------------------------------------------

class PaymentChangeRequest(Base, TimestampMixin):
    __tablename__ = "payment_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    requested_by_id = Column(Integer, ForeignKey("users.id"))

    method = Column(String(20), nullable=False)          # check, direct_deposit, cash, moncash, natcash
    bank_name = Column(String(150))
    account_number = Column(String(80))                  # kont labank OSWA telefòn MonCash/NatCash
    status = Column(String(12), default="pending", nullable=False, server_default="pending")

    decided_by_id = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime(timezone=True))
    decision_note = Column(Text)


# ---------------------------------------------------------------------------
# FOTO PWOFIL ANPLWAYE (routers/employee_photos.py)
# JPEG kare 256 px ke sèvè a te netwaye. `public_key` se kle aleyatwa ki nan
# lyen piblik la; li chanje chak fwa foto a chanje.
# ---------------------------------------------------------------------------

class EmployeePhoto(Base):
    __tablename__ = "employee_photos"

    employee_id = Column(Integer, ForeignKey("employees.id"), primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    data = Column(LargeBinary, nullable=False)
    public_key = Column(String(40), unique=True, index=True, nullable=False)
    sha256 = Column(String(64), nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KioskPairing(Base, TimestampMixin):
    """
    Kòd kout pou aktive yon tablèt: 6 karaktè ("K7P-4QX"), 10 minit, yon sèl fwa.
    Admin lan jenere l, li tape l sou tablèt la, tablèt la resevwa pwòp token pa l
    (routers/kiosk.py: /pairings ak /pair). Nou estoke sha256 kòd la sèlman.
    """
    __tablename__ = "kiosk_pairings"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    name = Column(String(100), nullable=False)              # non tablèt la ap genyen
    code_hash = Column(String(64), index=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    device_id = Column(Integer, ForeignKey("kiosk_devices.id"))


# ---------------------------------------------------------------------------
# AVANS SOU SALÈ (routers/salary_advances.py)
#
# Anplwaye a mande, manadjè a (oswa HR) apwouve, pewòl la retire yon vèsman
# sou chak fich jiskaske balans lan rive a 0. Balans = amount - sum(repayments).
# Estati se String (pa Enum PostgreSQL): pending, approved, repaid,
# rejected, cancelled, closed.
# ---------------------------------------------------------------------------

class SalaryAdvance(Base, TimestampMixin):
    __tablename__ = "salary_advances"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    requested_by_id = Column(Integer, ForeignKey("users.id"))

    amount = Column(Integer, nullable=False)                 # an santim
    installments = Column(Integer, nullable=False, default=1)
    installment_amount = Column(Integer, nullable=False)     # an santim, pa fich
    reason = Column(Text)
    status = Column(String(12), default="pending", nullable=False, server_default="pending")

    decided_by_id = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime(timezone=True))
    decision_note = Column(Text)
    closed_at = Column(DateTime(timezone=True))   # fin ranbouse, refize, anile oswa fèmen


class SalaryAdvanceRepayment(Base):
    """Yon retrè sou yon fich peye. Yon liy pa avans pa fich."""
    __tablename__ = "salary_advance_repayments"
    __table_args__ = (
        UniqueConstraint("advance_id", "payslip_id", name="uq_advance_repayment_slip"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), index=True, nullable=False)
    advance_id = Column(Integer, ForeignKey("salary_advances.id"), index=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), index=True, nullable=False)
    payslip_id = Column(Integer, ForeignKey("payslips.id"), index=True, nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    amount = Column(Integer, nullable=False)                 # an santim
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

# ---------------------------------------------------------------------------
# ESÈ KONEKSYON AK ENSKRIPSYON (app/login_guard.py)
#
# Yon liy pa esè. Sèvi pou: blokaj tanporè pa imel, limit pa IP, limit
# enskripsyon. Liy ki gen plis pase 2 jou efase otomatikman.
# ---------------------------------------------------------------------------

class AuthAttempt(Base):
    __tablename__ = "auth_attempts"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(10), nullable=False)               # "login" oswa "signup"
    ip_address = Column(String(45), index=True)
    email = Column(String(255), index=True)
    success = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, index=True)

# ---------------------------------------------------------------------------
# LYEN PA IMEL (app/email_tokens.py): chanje modpas, verifye imel.
# Nou sere sha256 lyen an sèlman. Yon lyen sèvi yon sèl fwa epi li ekspire.
# ---------------------------------------------------------------------------

class EmailToken(Base):
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    purpose = Column(String(10), nullable=False)             # "reset" oswa "verify"
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)

# ---------------------------------------------------------------------------
# KÒD SEKOU 2FA (routers/mfa.py): sha256 sèlman; chak kòd sèvi yon sèl fwa.
# ---------------------------------------------------------------------------

class RecoveryCode(Base):
    __tablename__ = "recovery_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    code_hash = Column(String(64), index=True, nullable=False)
    used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False)
