"""
Konbit — Router Tablo jesyon (administratè / HR)
Chemen: backend/app/routers/admin.py

    GET /api/admin/overview     Tout sa administratè a bezwen wè an yon kout je:
                                  - lis "Kòmanse ak KONMBIT" (5 etap + pwogrè)
                                  - chif yo: anplwaye, prezan jodi a, sa k ap tann
                                  - pwochen pewòl la (total oswa estimasyon)
                                  - dat limit deklarasyon ONA / OFATMA / DGI

DAT LIMIT DEKLARASYON YO — POU VERIFYE AK YON KONTAB AYISYEN:
  DECLARATION_DUE_DAY bay jou nan mwa APRE a kote deklarasyon an dwe fèt.
  Nou mete 15 pou tou 3 kòm pwen depa; yon kontab dwe konfime (oswa chanje)
  chif sa yo anvan yon vrè biznis konte sou yo.
  Montan yo: sa ki RETNI sou fich ki PEYE nan mwa a (dat peman LOKAL).
  ONA isit la se PATI ANPLWAYE A sèlman (6%) — pati anplwayè a poko kalkile.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..clock_mode import get_clock_mode
from ..deps import CurrentUser, DbSession, TenantId, require_hr
from ..models import (
    AttendanceStatus,
    AuditLog,
    Employee,
    LeaveBalance,
    LeaveType,
    PayPeriod,
    PayrollStatus,
    Payslip,
    TimeEntry,
)
from ..timezone_utils import get_local_today, get_org_timezone
from .team import inbox_count

router = APIRouter()

# Jou nan mwa APRE a — POU VERIFYE AK YON KONTAB (gade anlè a).
DECLARATION_DUE_DAY = {"DGI": 15, "ONA": 15, "OFATMA": 15}


def _as_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _month_add(d: date, months: int) -> date:
    """Premye jou mwa a, `months` mwa pita (oswa pi bonè)."""
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return date(y, m + 1, 1)


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

class OnboardingStep(BaseModel):
    key: str                      # employees | positions | leave_balances | clock_mode | pay_period
    done: bool
    progress: Optional[int] = None     # egz: 3 moun sou 5 gen yon pozisyon
    total: Optional[int] = None
    link: str


class Onboarding(BaseModel):
    steps: list[OnboardingStep]
    done_count: int
    total: int
    complete: bool


class Headcount(BaseModel):
    active: int
    on_payroll: int
    present_today: int
    still_working: int


class Pending(BaseModel):
    leaves: int
    timesheets: int
    total: int


class NextPayroll(BaseModel):
    period_id: int
    name: str
    start_date: date
    end_date: date
    pay_date: date
    status: PayrollStatus
    days_until_pay: int
    payslip_count: int
    total_gross: int              # an santim
    total_deductions: int
    total_net: int
    estimated: bool               # True: fich yo poko kalkile — nou estime ak salè yo


class Declaration(BaseModel):
    code: str                     # DGI | ONA | OFATMA
    for_month: str                # "2026-09" — mwa salè yo te peye
    due_date: date
    days_left: int
    amount: int                   # an santim, sa ki retni nan mwa a


class AdminOverview(BaseModel):
    today: date
    clock_mode: str
    onboarding: Onboarding
    headcount: Headcount
    pending: Pending
    next_payroll: Optional[NextPayroll] = None
    declarations: list[Declaration]


# ---------------------------------------------------------------------------
# ENDPOINT
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=AdminOverview, dependencies=[Depends(require_hr)])
def overview(user: CurrentUser, org_id: TenantId, db: DbSession):
    today = get_local_today(db, org_id)
    tz = get_org_timezone(db, org_id)

    active = db.query(Employee).filter(
        Employee.organization_id == org_id,
        Employee.is_active.is_(True),
    ).all()
    on_payroll = [e for e in active if e.on_payroll]

    # --- Prezans jodi a ---
    today_rows = db.query(TimeEntry.employee_id, TimeEntry.status).filter(
        TimeEntry.organization_id == org_id,
        TimeEntry.work_date == today,
    ).all()
    present = {r[0] for r in today_rows}
    working = {r[0] for r in today_rows if r[1] == AttendanceStatus.OPEN}

    # --- Kòmanse ak KONMBIT ---
    with_position = sum(1 for e in active if e.position_id)
    balances = {
        b.employee_id for b in db.query(LeaveBalance).filter(
            LeaveBalance.organization_id == org_id,
            LeaveBalance.leave_type == LeaveType.VACATION,
            LeaveBalance.year == today.year,
            LeaveBalance.entitled_days > 0,
        ).all()
    }
    with_balance = sum(1 for e in on_payroll if e.id in balances)
    clock_mode_chosen = db.query(AuditLog.id).filter(
        AuditLog.organization_id == org_id,
        AuditLog.entity_type == "organization",
        AuditLog.changes.like("clock_mode:%"),
    ).first() is not None
    has_period = db.query(PayPeriod.id).filter(PayPeriod.organization_id == org_id).first() is not None

    steps = [
        OnboardingStep(key="employees", done=len(active) > 0, link="employees.html"),
        OnboardingStep(key="positions", done=bool(active) and with_position == len(active),
                       progress=with_position, total=len(active), link="employees.html"),
        OnboardingStep(key="leave_balances", done=bool(on_payroll) and with_balance == len(on_payroll),
                       progress=with_balance, total=len(on_payroll), link="leave-balances.html"),
        OnboardingStep(key="clock_mode", done=clock_mode_chosen, link="kiosk-settings.html"),
        OnboardingStep(key="pay_period", done=has_period, link="payroll.html"),
    ]
    done_count = sum(1 for s in steps if s.done)

    # --- Sa k ap tann (menm kalkil ak ti chif meni an) ---
    box = inbox_count(user=user, org_id=org_id, db=db)

    # --- Pwochen pewòl la: premye peryòd ki poko peye ---
    next_payroll = None
    period = db.query(PayPeriod).filter(
        PayPeriod.organization_id == org_id,
        PayPeriod.status != PayrollStatus.PAID,
        PayPeriod.status != PayrollStatus.CANCELLED,
    ).order_by(PayPeriod.pay_date).first()
    if period is not None:
        slips = db.query(Payslip).filter(Payslip.pay_period_id == period.id).all()
        if slips:
            gross = sum(s.gross_amount or 0 for s in slips)
            net = sum(s.net_amount or 0 for s in slips)
            estimated = False
        else:
            # Estimasyon: salè fiks moun ki sou pewòl yo (moun pa lè yo pa ladan).
            gross = sum(e.base_salary or 0 for e in on_payroll)
            net = 0
            estimated = True
        next_payroll = NextPayroll(
            period_id=period.id, name=period.name,
            start_date=period.start_date, end_date=period.end_date,
            pay_date=period.pay_date, status=period.status,
            days_until_pay=(period.pay_date - today).days,
            payslip_count=len(slips),
            total_gross=gross,
            total_deductions=(gross - net) if not estimated else 0,
            total_net=net,
            estimated=estimated,
        )

    # --- Deklarasyon yo: mwa pase a si dat limit li poko rive, sinon mwa sa a ---
    paid = db.query(Payslip).filter(
        Payslip.organization_id == org_id,
        Payslip.status == PayrollStatus.PAID,
        Payslip.paid_at.isnot(None),
    ).all()
    declarations = []
    for code, day in DECLARATION_DUE_DAY.items():
        month_start = _month_add(today, -1)
        due = _month_add(month_start, 1).replace(day=day)
        if due < today:
            month_start = today.replace(day=1)
            due = _month_add(month_start, 1).replace(day=day)
        month_end = _month_add(month_start, 1) - timedelta(days=1)

        in_month = [
            s for s in paid
            if month_start <= _as_aware(s.paid_at).astimezone(tz).date() <= month_end
        ]
        if code == "DGI":
            amount = sum((s.tax_amount or 0) + (s.supplemental_tax_amount or 0) for s in in_month)
        elif code == "ONA":
            amount = sum(s.ona_amount or 0 for s in in_month)
        else:
            amount = sum(s.ofatma_amount or 0 for s in in_month)

        declarations.append(Declaration(
            code=code, for_month=f"{month_start:%Y-%m}", due_date=due,
            days_left=(due - today).days, amount=amount,
        ))

    return AdminOverview(
        today=today,
        clock_mode=get_clock_mode(db, org_id),
        onboarding=Onboarding(steps=steps, done_count=done_count, total=len(steps),
                              complete=done_count == len(steps)),
        headcount=Headcount(active=len(active), on_payroll=len(on_payroll),
                            present_today=len(present), still_working=len(working)),
        pending=Pending(leaves=box.leaves, timesheets=box.timesheets, total=box.total),
        next_payroll=next_payroll,
        declarations=declarations,
    )