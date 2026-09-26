"""
Konbit — Schemas Pydantic v2

Konvansyon:
  - `XxxCreate`  : sa kliyan an voye pou kreye
  - `XxxUpdate`  : tout chan opsyonèl, pou PATCH
  - `XxxOut`     : sa API a retounen
  - `XxxBrief`   : vèsyon kout pou lis ak referans

RÈG ENPÒTAN: `organization_id` PA JANM nan yon schema Create oswa Update.
Li soti nan token an (deps.get_tenant). Si ou aksepte l nan kò rekèt la,
nenpòt moun ka ekri done nan yon lòt biznis.

Lajan: tout chan `*_amount`, `salary`, `rate` se an SANTIM (Integer).

Dat ak lè: chan ki itilize `UtcDatetime` REFIZE dat san fizo orè, epi
konvèti tout lòt yo an UTC anvan yo rive nan baz done a.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from .models import (
    ApplicationStage,
    AttendanceStatus,
    Currency,
    EmploymentStatus,
    EmploymentType,
    FeedbackType,
    JobStatus,
    LeaveType,
    OfferStatus,
    PaymentMethod,
    PayrollStatus,
    RequestStatus,
    UserRole,
)

ORM = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# DAT AK FIZO ORÈ
# ---------------------------------------------------------------------------

def _require_utc(v: datetime) -> datetime:
    """
    Refize dat san fizo orè, epi konvèti tout lòt yo an UTC.

    Yon <input type="datetime-local"> voye "2026-10-01T10:00", san fizo orè.
    Si nou sere sa, frontend la li l tounen kòm UTC epi lè a deplase 4-5 èdtan.
    SQLite pa sere fizo orè a non plis, kidonk nou toujou sere an UTC.
    """
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("Dat la dwe gen fizo orè (egz: 2026-10-01T14:00:00Z).")
    return v.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


def _require_http_url(v: str) -> Optional[str]:
    """
    Aksepte SÈLMAN lyen http:// oswa https://.

    Lyen sa yo soti nan moun deyò (paj karyè piblik la). Yon lyen
    "javascript:..." ta egzekite kòd nan navigatè HR la si yon paj
    ta mete l nan yon <a href>. Frontend la deja bloke sa, men nou
    refize l isit tou pou li pa janm antre nan baz done a.
    """
    v = (v or "").strip()
    if not v:
        return None
    if not v.lower().startswith(("http://", "https://")) or len(v) < 11:
        raise ValueError("Lyen an dwe kòmanse ak https:// (oswa http://).")
    # Longè a tcheke ISIT, pa ak Field(max_length=...): Pydantic aplike
    # max_length APRE validatè sa a, epi li pa ka mezire yon None
    # (lyen vid la) — sa te bay yon erè 500.
    if len(v) > 500:
        raise ValueError("Lyen an twò long (500 karaktè maksimòm).")
    return v


HttpUrlStr = Annotated[str, AfterValidator(_require_http_url)]


# ---------------------------------------------------------------------------
# JENERIK
# ---------------------------------------------------------------------------

class Message(BaseModel):
    detail: str


class Page(BaseModel):
    """Anvlòp pou lis long."""
    total: int
    page: int
    size: int
    items: list


# ---------------------------------------------------------------------------
# OTANTIFIKASYON
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=128)


class UserBrief(BaseModel):
    model_config = ORM
    id: int
    email: EmailStr
    full_name: str
    role: UserRole


class UserOut(UserBrief):
    organization_id: Optional[int] = None
    preferred_language: str = "ht"
    is_active: bool
    email_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    full_name: str = Field(min_length=2, max_length=200)
    role: UserRole = UserRole.EMPLOYEE
    preferred_language: str = "ht"


# ---------------------------------------------------------------------------
# ÒGANIZASYON
# ---------------------------------------------------------------------------

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: str = "HT"
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    default_currency: Currency = Currency.HTG


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    industry: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    logo_url: Optional[str] = None
    default_currency: Optional[Currency] = None
    timezone: Optional[str] = None


class OrganizationOut(BaseModel):
    model_config = ORM
    id: int
    name: str
    slug: str
    legal_name: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    country: str
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_url: Optional[str] = None
    default_currency: Currency
    timezone: str
    is_active: bool
    created_at: datetime


class SignupRequest(BaseModel):
    """Yon biznis ki enskri: kreye Organization + premye ORG_ADMIN lan."""
    organization: OrganizationCreate
    admin_full_name: str = Field(min_length=2, max_length=200)
    admin_email: EmailStr
    admin_password: str = Field(min_length=10, max_length=128)


# ---------------------------------------------------------------------------
# DEPATMAN AK POZISYON
# ---------------------------------------------------------------------------

class DepartmentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None
    is_active: Optional[bool] = None


class DepartmentOut(BaseModel):
    model_config = ORM
    id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    head_employee_id: Optional[int] = None
    is_active: bool


class PositionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    department_id: Optional[int] = None
    level: Optional[str] = None
    description: Optional[str] = None
    min_salary: Optional[int] = Field(default=None, ge=0)
    max_salary: Optional[int] = Field(default=None, ge=0)
    currency: Currency = Currency.HTG

    @model_validator(mode="after")
    def check_salary_range(self):
        if self.min_salary and self.max_salary and self.min_salary > self.max_salary:
            raise ValueError("Salè minimòm nan pa ka pi wo pase salè maksimòm nan.")
        return self


class PositionOut(BaseModel):
    model_config = ORM
    id: int
    title: str
    department_id: Optional[int] = None
    level: Optional[str] = None
    description: Optional[str] = None
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    currency: Currency
    is_active: bool


# ---------------------------------------------------------------------------
# ANPLWAYE
# ---------------------------------------------------------------------------

class EmployeeBrief(BaseModel):
    """Vèsyon san done sansib — pou òganigram ak lis."""
    model_config = ORM
    id: int
    employee_number: str
    first_name: str
    last_name: str
    photo_url: Optional[str] = None
    position_id: Optional[int] = None
    department_id: Optional[int] = None
    manager_id: Optional[int] = None
    status: EmploymentStatus


class EmployeeCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    employee_number: Optional[str] = None      # jenere otomatikman si vid
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    national_id: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_id: Optional[int] = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    hire_date: date

    base_salary: Optional[int] = Field(default=None, ge=0, description="An santim")
    hourly_rate: Optional[int] = Field(default=None, ge=0, description="An santim")
    currency: Currency = Currency.HTG

    preferred_payment_method: PaymentMethod = PaymentMethod.CHECK
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mobile_money_number: Optional[str] = None

    # Kont koneksyon
    create_login: bool = True
    login_email: Optional[EmailStr] = None
    login_role: UserRole = UserRole.EMPLOYEE

    @field_validator("date_of_birth")
    @classmethod
    def must_be_adult(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return v
        age = (date.today() - v).days / 365.25
        if age < 16:
            raise ValueError("Anplwaye a dwe gen omwen 16 an.")
        if age > 100:
            raise ValueError("Dat nesans lan pa sanble kòrèk.")
        return v

    @model_validator(mode="after")
    def login_needs_email(self):
        if self.create_login and not (self.login_email or self.personal_email):
            raise ValueError("Ou bezwen yon imel pou kreye kont koneksyon an.")
        return self


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    personal_email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    photo_url: Optional[str] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    manager_id: Optional[int] = None
    employment_type: Optional[EmploymentType] = None
    status: Optional[EmploymentStatus] = None
    base_salary: Optional[int] = Field(default=None, ge=0)
    hourly_rate: Optional[int] = Field(default=None, ge=0)
    preferred_payment_method: Optional[PaymentMethod] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    mobile_money_number: Optional[str] = None


class EmployeeOut(EmployeeBrief):
    """Dosye konplè — SÈLMAN pou HR, admin, manadjè a, ak anplwaye a limenm."""
    organization_id: int
    user_id: Optional[int] = None
    personal_email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    city: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    employment_type: EmploymentType
    hire_date: date
    termination_date: Optional[date] = None
    base_salary: Optional[int] = None
    hourly_rate: Optional[int] = None
    currency: Currency
    preferred_payment_method: PaymentMethod
    bank_name: Optional[str] = None
    mobile_money_number: Optional[str] = None
    is_active: bool
    created_at: datetime

    # Nou PA ekspoze `national_id` ni `bank_account_number` isit.
    # Fè yon endpoint separe ak jounal odit si HR bezwen yo.


class TerminationRequest(BaseModel):
    termination_date: date
    reason: str = Field(min_length=3)
    deactivate_login: bool = True


# ---------------------------------------------------------------------------
# ÒGANIGRAM
# ---------------------------------------------------------------------------

class OrgNode(BaseModel):
    """Yon nœud nan pyebwa òganigram lan."""
    id: int
    full_name: str
    employee_number: str
    position_title: Optional[str] = None
    department_name: Optional[str] = None
    photo_url: Optional[str] = None
    reports: list["OrgNode"] = []


class ManagementChain(BaseModel):
    """Tout moun ki sou tèt yon anplwaye, soti nan manadjè dirèk jouk anwo."""
    employee: EmployeeBrief
    chain: list[EmployeeBrief]


# ---------------------------------------------------------------------------
# REKRITMAN
# ---------------------------------------------------------------------------

class JobPostingCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    location: Optional[str] = None
    is_remote: bool = False
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    salary_min: Optional[int] = Field(default=None, ge=0)
    salary_max: Optional[int] = Field(default=None, ge=0)
    currency: Currency = Currency.HTG
    show_salary: bool = False
    openings: int = Field(default=1, ge=1)
    closes_at: Optional[UtcDatetime] = None


class JobPostingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    show_salary: Optional[bool] = None
    openings: Optional[int] = None
    status: Optional[JobStatus] = None
    closes_at: Optional[UtcDatetime] = None


class JobPostingPublic(BaseModel):
    """Sa moun deyò wè sou paj karyè a."""
    model_config = ORM
    id: int
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    location: Optional[str] = None
    is_remote: bool
    employment_type: EmploymentType
    openings: int
    published_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    company_name: Optional[str] = None
    # Ranpli SÈLMAN lè HR tcheke `show_salary` (gade jobs._to_public)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[Currency] = None


class JobPostingOut(JobPostingPublic):
    organization_id: int
    department_id: Optional[int] = None
    position_id: Optional[int] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Currency
    show_salary: bool
    status: JobStatus
    view_count: int
    application_count: int = 0
    created_at: datetime


class ApplicationCreate(BaseModel):
    """Moun deyò ka voye sa — pa gen otantifikasyon."""
    job_posting_id: int
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    resume_url: Optional[HttpUrlStr] = None
    cover_letter: Optional[str] = None
    source: Optional[str] = None


class ApplicationUpdate(BaseModel):
    stage: Optional[ApplicationStage] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    internal_notes: Optional[str] = None
    rejected_reason: Optional[str] = None


class ApplicationOut(BaseModel):
    model_config = ORM
    id: int
    job_posting_id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    resume_url: Optional[str] = None
    cover_letter: Optional[str] = None
    stage: ApplicationStage
    rating: Optional[int] = None
    source: Optional[str] = None
    created_at: datetime


class InterviewCreate(BaseModel):
    application_id: int
    interviewer_id: Optional[int] = None
    scheduled_at: UtcDatetime
    duration_minutes: int = Field(default=45, ge=5, le=480)
    location: Optional[str] = None
    round_number: int = Field(default=1, ge=1)


class InterviewOut(BaseModel):
    model_config = ORM
    id: int
    application_id: int
    interviewer_id: Optional[int] = None
    scheduled_at: datetime
    duration_minutes: int
    location: Optional[str] = None
    round_number: int
    notes: Optional[str] = None
    score: Optional[int] = None
    completed: bool


class OfferCreate(BaseModel):
    application_id: int
    salary: int = Field(ge=0, description="An santim")
    currency: Currency = Currency.HTG
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    start_date: Optional[date] = None
    expires_at: Optional[UtcDatetime] = None
    notes: Optional[str] = None


class OfferOut(BaseModel):
    model_config = ORM
    id: int
    application_id: int
    salary: int
    currency: Currency
    employment_type: EmploymentType
    start_date: Optional[date] = None
    expires_at: Optional[datetime] = None
    status: OfferStatus
    document_url: Optional[str] = None
    responded_at: Optional[datetime] = None
    created_at: datetime


class OfferResponse(BaseModel):
    accept: bool
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# PREZANS (CLOCK IN / CLOCK OUT)
# ---------------------------------------------------------------------------

class ClockInRequest(BaseModel):
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    device_info: Optional[str] = None


class ClockOutRequest(BaseModel):
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    break_minutes: int = Field(default=0, ge=0, le=480)


class TimeEntryOut(BaseModel):
    model_config = ORM
    id: int
    employee_id: int
    work_date: date
    clock_in_at: datetime
    clock_out_at: Optional[datetime] = None
    break_minutes: int
    worked_minutes: Optional[int] = None
    overtime_minutes: int
    status: AttendanceStatus
    adjustment_reason: Optional[str] = None


class TimeEntryAdjust(BaseModel):
    """HR sèlman. `reason` obligatwa — li ale nan jounal odit la."""
    clock_in_at: Optional[datetime] = None
    clock_out_at: Optional[datetime] = None
    break_minutes: Optional[int] = Field(default=None, ge=0)
    reason: str = Field(min_length=5)


class AttendanceSummary(BaseModel):
    employee_id: int
    period_start: date
    period_end: date
    days_present: int
    days_absent: int
    total_worked_minutes: int
    total_overtime_minutes: int
    late_arrivals: int


# ---------------------------------------------------------------------------
# KONJE
# ---------------------------------------------------------------------------

class LeaveRequestCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: Optional[str] = None
    attachment_url: Optional[str] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Dat fen an pa ka anvan dat kòmansman an.")
        if (self.end_date - self.start_date).days > 365:
            raise ValueError("Yon demann konje pa ka depase yon ane.")
        return self


class LeaveDecision(BaseModel):
    approve: bool
    note: Optional[str] = None


class LeaveRequestOut(BaseModel):
    model_config = ORM
    id: int
    employee_id: int
    leave_type: LeaveType
    start_date: date
    end_date: date
    total_days: float
    reason: Optional[str] = None
    attachment_url: Optional[str] = None
    status: RequestStatus
    approver_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime


class LeaveBalanceOut(BaseModel):
    model_config = ORM
    leave_type: LeaveType
    year: int
    entitled_days: float
    used_days: float
    carried_over_days: float

    @property
    def remaining_days(self) -> float:
        return float(self.entitled_days) + float(self.carried_over_days) - float(self.used_days)


# ---------------------------------------------------------------------------
# PEWÒL
# ---------------------------------------------------------------------------

class PayPeriodCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    pay_date: date

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Dat fen an pa ka anvan dat kòmansman an.")
        if self.pay_date < self.end_date:
            raise ValueError("Dat peyman an pa ka anvan fen peryòd la.")
        return self


class PayPeriodOut(BaseModel):
    model_config = ORM
    id: int
    name: str
    start_date: date
    end_date: date
    pay_date: date
    status: PayrollStatus
    payslip_count: int = 0
    total_net: int = 0


class PayslipOut(BaseModel):
    """Se sa anplwaye a wè — li di l si se chèk oubyen depo."""
    model_config = ORM
    id: int
    pay_period_id: int
    employee_id: int
    base_amount: int
    overtime_amount: int
    bonus_amount: int
    gross_amount: int
    tax_amount: int                  # IRI sou salè regilye a
    supplemental_tax_amount: int = 0 # Retni fiks sou bonis / èdtan siplemantè
    ona_amount: int
    ofatma_amount: int
    cfgdct_amount: int = 0           # Kolektivite teritoryal, 1%
    fdu_cas_amount: int = 0          # Fon dijans + Kès Asistans Sosyal, 1%
    other_deductions: int
    net_amount: int
    currency: Currency
    hours_worked: Optional[float] = None
    overtime_hours: Optional[float] = None
    payment_method: PaymentMethod
    check_number: Optional[str] = None
    bank_name: Optional[str] = None
    account_last4: Optional[str] = None
    transaction_ref: Optional[str] = None
    paid_at: Optional[datetime] = None
    status: PayrollStatus
    pdf_url: Optional[str] = None


class PayslipAdjust(BaseModel):
    bonus_amount: Optional[int] = Field(default=None, ge=0)
    other_deductions: Optional[int] = Field(default=None, ge=0)
    payment_method: Optional[PaymentMethod] = None
    check_number: Optional[str] = None
    notes: Optional[str] = None


class PayrollRunRequest(BaseModel):
    """Jenere tout fich peye yo pou yon peryòd."""
    pay_period_id: int
    employee_ids: Optional[list[int]] = None   # None = tout anplwaye aktif
    include_overtime: bool = True


# ---------------------------------------------------------------------------
# FÒMASYON
# ---------------------------------------------------------------------------

class LessonCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    video_url: Optional[str] = None
    attachment_url: Optional[str] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    order_index: int = 0
    is_required: bool = True


class LessonOut(BaseModel):
    model_config = ORM
    id: int
    course_id: int
    title: str
    description: Optional[str] = None
    video_url: Optional[str] = None
    attachment_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    order_index: int
    is_required: bool


class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: str = "ht"
    is_mandatory: bool = False
    target_department_id: Optional[int] = None
    passing_score: int = Field(default=70, ge=0, le=100)


class CourseOut(BaseModel):
    model_config = ORM
    id: int
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    thumbnail_url: Optional[str] = None
    language: str
    is_mandatory: bool
    passing_score: int
    is_published: bool
    lesson_count: int = 0
    total_duration_seconds: int = 0


class CourseDetail(CourseOut):
    lessons: list[LessonOut] = []


class EnrollmentCreate(BaseModel):
    course_id: int
    employee_ids: list[int] = Field(min_length=1)
    due_date: Optional[date] = None


class EnrollmentOut(BaseModel):
    model_config = ORM
    id: int
    course_id: int
    employee_id: int
    due_date: Optional[date] = None
    progress_percent: int
    completed_at: Optional[datetime] = None
    score: Optional[int] = None
    certificate_url: Optional[str] = None


class ProgressUpdate(BaseModel):
    """Frontend lan voye sa chak 15-30 segonn pandan videyo a ap jwe."""
    lesson_id: int
    last_position_seconds: int = Field(ge=0)
    seconds_watched: int = Field(ge=0)
    completed: bool = False


# ---------------------------------------------------------------------------
# FIDBAK AK PÈFÒMANS
# ---------------------------------------------------------------------------

class FeedbackCreate(BaseModel):
    subject_employee_id: Optional[int] = None
    feedback_type: FeedbackType = FeedbackType.SUGGESTION
    title: Optional[str] = Field(default=None, max_length=200)
    body: str = Field(min_length=5)
    is_anonymous: bool = False
    is_private: bool = True


class FeedbackOut(BaseModel):
    model_config = ORM
    id: int
    feedback_type: FeedbackType
    title: Optional[str] = None
    body: str
    is_anonymous: bool
    is_private: bool
    subject_employee_id: Optional[int] = None
    author: Optional[EmployeeBrief] = None      # None si anonim
    acknowledged_at: Optional[datetime] = None
    response: Optional[str] = None
    created_at: datetime


class FeedbackRespond(BaseModel):
    response: str = Field(min_length=2)


class PerformanceReviewCreate(BaseModel):
    employee_id: int
    period_label: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    overall_score: Optional[int] = Field(default=None, ge=1, le=5)
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals: Optional[str] = None


class PerformanceReviewOut(BaseModel):
    model_config = ORM
    id: int
    employee_id: int
    reviewer_id: Optional[int] = None
    period_label: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    overall_score: Optional[int] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    goals: Optional[str] = None
    employee_comment: Optional[str] = None
    status: RequestStatus
    finalized_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# NOTIFIKASYON AK DOKIMAN
# ---------------------------------------------------------------------------

class NotificationOut(BaseModel):
    model_config = ORM
    id: int
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    category: Optional[str] = None
    is_read: bool
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ORM
    id: int
    employee_id: Optional[int] = None
    name: str
    category: Optional[str] = None
    file_url: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    expires_at: Optional[date] = None
    is_confidential: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# TABLO DE BÒ
# ---------------------------------------------------------------------------

class EmployeeDashboard(BaseModel):
    employee: EmployeeBrief
    clocked_in: bool
    today_entry: Optional[TimeEntryOut] = None
    pending_leave_requests: int
    leave_balances: list[LeaveBalanceOut] = []
    pending_courses: int
    latest_payslip: Optional[PayslipOut] = None
    unread_notifications: int


class HRDashboard(BaseModel):
    total_employees: int
    active_employees: int
    on_leave_today: int
    clocked_in_now: int
    open_positions: int
    pending_applications: int
    pending_leave_requests: int
    upcoming_pay_date: Optional[date] = None


OrgNode.model_rebuild()